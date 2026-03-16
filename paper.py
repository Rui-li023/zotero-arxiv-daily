from typing import Optional
from functools import cached_property
from tempfile import TemporaryDirectory
import arxiv
import tarfile
import re
from llm import get_llm
import requests
from requests.adapters import HTTPAdapter, Retry
from loguru import logger
import tiktoken
from contextlib import ExitStack
import time
from bs4 import BeautifulSoup

class ArxivPaper:
    def __init__(self,paper:arxiv.Result):
        self._paper = paper
        self._data = None
        self.score = None
    
    @property
    def title(self) -> str:
        if self._paper is None:
            return self._data["title"]
        return self._paper.title

    @property
    def summary(self) -> str:
        if self._paper is None:
            return self._data["summary"]
        return self._paper.summary

    @property
    def authors(self) -> list[str]:
        if self._paper is None:
            return self._data["authors"]
        return self._paper.authors

    @cached_property
    def arxiv_id(self) -> str:
        if self._paper is None:
            return self._data["arxiv_id"]
        return re.sub(r'v\d+$', '', self._paper.get_short_id())

    @property
    def pdf_url(self) -> str:
        if self._paper is None:
            return self._data["pdf_url"]
        return self._paper.pdf_url
    
    @cached_property
    def code_url(self) -> Optional[str]:
        if self._paper is None:
            return self._data.get("code_url")
        s = requests.Session()
        retries = Retry(total=5, backoff_factor=0.1)
        s.mount('https://', HTTPAdapter(max_retries=retries))
        try:
            paper_list = s.get(f'https://paperswithcode.com/api/v1/papers/?arxiv_id={self.arxiv_id}').json()
        except Exception as e:
            logger.debug(f'Error when searching {self.arxiv_id}: {e}')
            return None

        if paper_list.get('count',0) == 0:
            return None
        paper_id = paper_list['results'][0]['id']

        try:
            repo_list = s.get(f'https://paperswithcode.com/api/v1/papers/{paper_id}/repositories/').json()
        except Exception as e:
            logger.debug(f'Error when searching {self.arxiv_id}: {e}')
            return None
        if repo_list.get('count',0) == 0:
            return None
        return repo_list['results'][0]['url']
    
    @cached_property
    def tex(self) -> dict[str,str]:
        with ExitStack() as stack:
            tmpdirname = stack.enter_context(TemporaryDirectory())
            # 添加重试逻辑
            max_retries = 5
            retry_count = 0
            base_delay = 1  # 基础延迟1秒
            
            while retry_count < max_retries:
                try:
                    file = self._paper.download_source(dirpath=tmpdirname)
                    break
                except Exception as e:
                    retry_count += 1
                    if retry_count == max_retries:
                        logger.error(f"Failed to download source for {self.arxiv_id} after {max_retries} retries: {e}")
                        return None
                    
                    delay = base_delay * (2 ** (retry_count - 1))  # 指数退避
                    logger.warning(f"Download attempt {retry_count} failed for {self.arxiv_id}: {e}. Retrying in {delay} seconds...")
                    time.sleep(delay)
            
            try:
                tar = stack.enter_context(tarfile.open(file))
            except tarfile.ReadError:
                logger.debug(f"Failed to find main tex file of {self.arxiv_id}: Not a tar file.")
                return None
 
            tex_files = [f for f in tar.getnames() if f.endswith('.tex')]
            if len(tex_files) == 0:
                logger.debug(f"Failed to find main tex file of {self.arxiv_id}: No tex file.")
                return None
            
            bbl_file = [f for f in tar.getnames() if f.endswith('.bbl')]
            match len(bbl_file) :
                case 0:
                    if len(tex_files) > 1:
                        logger.debug(f"Cannot find main tex file of {self.arxiv_id} from bbl: There are multiple tex files while no bbl file.")
                        main_tex = None
                    else:
                        main_tex = tex_files[0]
                case 1:
                    main_name = bbl_file[0].replace('.bbl','')
                    main_tex = f"{main_name}.tex"
                    if main_tex not in tex_files:
                        logger.debug(f"Cannot find main tex file of {self.arxiv_id} from bbl: The bbl file does not match any tex file.")
                        main_tex = None
                case _:
                    logger.debug(f"Cannot find main tex file of {self.arxiv_id} from bbl: There are multiple bbl files.")
                    main_tex = None
            if main_tex is None:
                logger.debug(f"Trying to choose tex file containing the document block as main tex file of {self.arxiv_id}")
            #read all tex files
            file_contents = {}
            for t in tex_files:
                f = tar.extractfile(t)
                content = f.read().decode('utf-8',errors='ignore')
                #remove comments
                content = re.sub(r'%.*\n', '\n', content)
                content = re.sub(r'\\begin{comment}.*?\\end{comment}', '', content, flags=re.DOTALL)
                content = re.sub(r'\\iffalse.*?\\fi', '', content, flags=re.DOTALL)
                #remove redundant \n
                content = re.sub(r'\n+', '\n', content)
                content = re.sub(r'\\\\', '', content)
                #remove consecutive spaces
                content = re.sub(r'[ \t\r\f]{3,}', ' ', content)
                if main_tex is None and re.search(r'\\begin\{document\}', content):
                    main_tex = t
                    logger.debug(f"Choose {t} as main tex file of {self.arxiv_id}")
                file_contents[t] = content
            
            if main_tex is not None:
                main_source:str = file_contents[main_tex]
                #find and replace all included sub-files
                include_files = re.findall(r'\\input\{(.+?)\}', main_source) + re.findall(r'\\include\{(.+?)\}', main_source)
                for f in include_files:
                    if not f.endswith('.tex'):
                        file_name = f + '.tex'
                    else:
                        file_name = f
                    main_source = main_source.replace(f'\\input{{{f}}}', file_contents.get(file_name, ''))
                file_contents["all"] = main_source
            else:
                logger.debug(f"Failed to find main tex file of {self.arxiv_id}: No tex file containing the document block.")
                file_contents["all"] = None
        return file_contents
    
    @cached_property
    def highlight(self) -> str:
        """生成一句话论文亮点"""
        if self._paper is None:
            return self._data.get("highlight", "")
        try:
            llm = get_llm()
            prompt = f"""
标题: {self.title}
摘要: {self.summary}

请用一句话（严格限制在50字以内）概括这篇论文的核心创新点。要求：
1. 突出最关键的技术创新
2. 极度简洁，直击要点
3. 只返回一句话，不要引号、不要任何其他内容
"""
            highlight = llm.generate(
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位资深的AI研究员，擅长用一句话抓住论文核心。你的回答必须简洁，不超过50字。",
                    },
                    {"role": "user", "content": prompt},
                ]
            )
            logger.info(f"Generated highlight for {self.arxiv_id}")
            
            # 过滤思考标签
            result = re.sub(r'<think>.*?</think>', '', highlight, flags=re.DOTALL | re.IGNORECASE)
            result = result.strip().strip('"').strip('"').strip('"')
            
            # 强制截断，确保不超过80字符
            if len(result) > 80:
                result = result[:77] + "..."
            return result
        except Exception as e:
            logger.warning(f"Failed to generate highlight for {self.arxiv_id}: {e}")
            return "论文简介暂时无法生成"

    @cached_property
    def tldr(self) -> str:
        if self._paper is None:
            return self._data.get("tldr", "")
        try:
            introduction = ""
            conclusion = ""
            if self.tex is not None:
                content = self.tex.get("all")
                if content is None:
                    content = "\n".join(self.tex.values())
                #remove cite
                content = re.sub(r'~?\\cite.?\{.*?\}', '', content)
                #remove figure
                content = re.sub(r'\\begin\{figure\}.*?\\end\{figure\}', '', content, flags=re.DOTALL)
                #remove table
                content = re.sub(r'\\begin\{table\}.*?\\end\{table\}', '', content, flags=re.DOTALL)
                #find introduction and conclusion
                match = re.search(r'\\section\{Introduction\}.*?(\\section|\\end\{document\}|\\bibliography|\\appendix|$)', content, flags=re.DOTALL)
                if match:
                    introduction = match.group(0)
                match = re.search(r'\\section\{Conclusion\}.*?(\\section|\\end\{document\}|\\bibliography|\\appendix|$)', content, flags=re.DOTALL)
                if match:
                    conclusion = match.group(0)
            llm = get_llm()
            prompt = f"""
# 待分析论文
标题: {self.title}
摘要: {self.summary}
引言: {introduction}
结论: {conclusion}

# 输出要求
请严格按照以下HTML模板输出论文分析，不要修改HTML结构和class名称：

<div class="paper-analysis">
  <div class="section">
    <h3>核心创新</h3>
    <p>[用2-3句话说明论文的核心创新点和技术贡献]</p>
  </div>
  
  <div class="section">
    <h3>技术细节</h3>
    <ul>
      <li><strong>问题定义：</strong>[论文要解决的核心问题]</li>
      <li><strong>方法概述：</strong>[提出的方法或架构的简要描述]</li>
      <li><strong>关键技术：</strong>[使用的关键技术或算法]</li>
    </ul>
  </div>
  
  <div class="section">
    <h3>实验与结果</h3>
    <p>[实验设置和主要结果，包括与baseline的对比]</p>
  </div>
  
  <div class="section">
    <h3>优势与局限</h3>
    <ul>
      <li><strong>优势：</strong>[论文的主要优势]</li>
      <li><strong>局限：</strong>[可能存在的问题或局限性]</li>
    </ul>
  </div>
  
  <div class="section">
    <h3>相关方向</h3>
    <p><strong>关键词：</strong>[5-8个相关研究关键词，用逗号分隔]</p>
  </div>
</div>

# 注意事项
1. 严格遵循上述HTML结构，不要添加或删除section
2. 使用专业、简洁的中文学术语言
3. 每个部分内容要具体、有信息量
4. 不要使用代码块包裹，直接输出HTML
"""
            
            tldr = llm.generate(
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位资深的人工智能研究员，擅长深度分析论文并提炼关键信息。你必须严格按照用户提供的HTML模板输出结果。",
                    },
                    {"role": "user", "content": prompt},
                ]
            )
            logger.info(f"Generated TLDR for {self.arxiv_id}")
            
            # 过滤思考标签
            tldr = re.sub(r'<think>.*?</think>', '', tldr, flags=re.DOTALL | re.IGNORECASE)
            
            # 提取HTML内容
            fenced_contents = re.findall(r"```html\s*(.*?)```", tldr, flags=re.DOTALL | re.IGNORECASE)
            if fenced_contents:
                tldr = fenced_contents[0]
            
            # 确保包含必要的div结构
            if '<div class="paper-analysis">' not in tldr:
                # 如果LLM没有按模板输出，尝试包装它
                tldr = f'<div class="paper-analysis">{tldr}</div>'
            
            return tldr
        except Exception as e:
            logger.warning(f"Failed to generate TLDR for {self.arxiv_id} due to API error: {e}")
            # 返回摘要作为后备
            return f'<div class="paper-analysis"><div class="section"><p>{self.summary}</p></div></div>'

    def to_dict(self) -> dict:
        """Serialize paper data to a dictionary. Call after cached_properties are computed."""
        authors = [a.name if hasattr(a, 'name') else str(a) for a in self.authors]
        data = {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "summary": self.summary,
            "authors": authors,
            "pdf_url": self.pdf_url,
            "score": self.score,
        }
        # Only include cached_properties that have been computed
        if "code_url" in self.__dict__:
            data["code_url"] = self.__dict__["code_url"]
        if "affiliations" in self.__dict__:
            data["affiliations"] = self.__dict__["affiliations"]
        if "highlight" in self.__dict__:
            data["highlight"] = self.__dict__["highlight"]
        if "tldr" in self.__dict__:
            data["tldr"] = self.__dict__["tldr"]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ArxivPaper":
        """Create a lightweight ArxivPaper from a serialized dictionary."""
        paper = object.__new__(cls)
        paper._paper = None
        paper.score = data.get("score")
        paper._data = data
        return paper

    @cached_property
    def affiliations(self) -> Optional[list[str]]:
        if self._paper is None:
            return self._data.get("affiliations")
        try:
            if self.tex is not None:
                content = self.tex.get("all")
                if content is None:
                    content = "\n".join(self.tex.values())
                #search for affiliations - only look at the beginning part
                possible_regions = [r'\\author.*?\\maketitle',r'\\begin{document}.*?\\begin{abstract}']
                matches = [re.search(p, content[:2000], flags=re.DOTALL) for p in possible_regions]
                match = next((m for m in matches if m), None)
                if match:
                    information_region = match.group(0)
                else:
                    logger.debug(f"Failed to extract affiliations of {self.arxiv_id}: No author information found.")
                    return None
                prompt = f"Given the author information of a paper in latex format, extract the affiliations of the authors in a python list format, which is sorted by the author order. If there is no affiliation found, return an empty list '[]'. Following is the author information:\n{information_region}"
                llm = get_llm()
                affiliations = llm.generate(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are an assistant who perfectly extracts affiliations of authors from the author information of a paper. You should return a python list of affiliations sorted by the author order, like ['TsingHua University','Peking University']. If an affiliation is consisted of multi-level affiliations, like 'Department of Computer Science, TsingHua University', you should return the top-level affiliation 'TsingHua University' only. Do not contain duplicated affiliations. If there is no affiliation found, you should return an empty list [ ]. You should only return the final list of affiliations, and do not return any intermediate results.",
                        },
                        {"role": "user", "content": prompt},
                    ]
                )

                try:
                    affiliations = re.search(r'\[.*?\]', affiliations, flags=re.DOTALL).group(0)
                    affiliations = eval(affiliations)
                    affiliations = list(set(affiliations))
                    affiliations = [str(a) for a in affiliations]
                    # print(affiliations)
                except Exception as e:
                    logger.debug(f"Failed to extract affiliations of {self.arxiv_id}: {e}")
                    return None
                return affiliations
        except Exception as e:
            logger.warning(f"Failed to get affiliations for {self.arxiv_id} due to API error: {e}")
            return None

    @cached_property
    def full_text(self) -> Optional[str]:
        """从arXiv HTML页面获取论文全文"""
        if self._paper is None:
            return self._data.get("full_text")

        try:
            # 尝试获取HTML版本
            url = f"https://arxiv.org/html/{self.arxiv_id}"
            s = requests.Session()
            retries = Retry(total=3, backoff_factor=1)
            s.mount('https://', HTTPAdapter(max_retries=retries))

            resp = s.get(url, timeout=30)
            if resp.status_code != 200:
                logger.debug(f"HTML version not available for {self.arxiv_id}: HTTP {resp.status_code}")
                return None

            soup = BeautifulSoup(resp.text, 'html.parser')

            # 找到主文档内容
            article = soup.find('article', class_='ltx_document')
            if not article:
                logger.debug(f"Could not find article content for {self.arxiv_id}")
                return None

            # 提取章节内容（排除导航、脚注、参考文献等）
            sections_text = []

            # 提取摘要
            abstract = article.find('div', class_='ltx_abstract')
            if abstract:
                abstract_text = abstract.get_text(separator=' ', strip=True)
                sections_text.append(f"Abstract:\n{abstract_text}")

            # 提取各章节
            for section in article.find_all('section', class_='ltx_section'):
                # 获取章节标题
                title_elem = section.find(['h2', 'h3', 'h4'], class_=re.compile(r'ltx_title'))
                section_title = title_elem.get_text(strip=True) if title_elem else ""

                # 获取章节内容（段落）
                paragraphs = []
                for para in section.find_all('div', class_='ltx_para'):
                    para_text = para.get_text(separator=' ', strip=True)
                    if para_text:
                        paragraphs.append(para_text)

                if paragraphs:
                    section_content = f"\n{section_title}\n" + "\n".join(paragraphs)
                    sections_text.append(section_content)

            full_text = "\n\n".join(sections_text)

            # 清理多余空白
            full_text = re.sub(r'\n{3,}', '\n\n', full_text)
            full_text = re.sub(r' {2,}', ' ', full_text)

            logger.info(f"Extracted full text for {self.arxiv_id} ({len(full_text)} chars)")
            return full_text

        except Exception as e:
            logger.warning(f"Failed to get full text for {self.arxiv_id}: {e}")
            return None
