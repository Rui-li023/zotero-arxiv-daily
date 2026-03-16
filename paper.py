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

class ArxivPaper:
    def __init__(self,paper:arxiv.Result):
        self._paper = paper
        self.score = None
    
    @property
    def title(self) -> str:
        return self._paper.title
    
    @property
    def summary(self) -> str:
        return self._paper.summary
    
    @property
    def authors(self) -> list[str]:
        return self._paper.authors
    
    @cached_property
    def arxiv_id(self) -> str:
        return re.sub(r'v\d+$', '', self._paper.get_short_id())
    
    @property
    def pdf_url(self) -> str:
        return self._paper.pdf_url
    
    @cached_property
    def code_url(self) -> Optional[str]:
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
    def tldr(self) -> str:
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
# 任务指令
1. **深度思考 (Think)**：不要只是复述摘要。请分析作者为什么选择这个方法？其核心假设是否存在漏洞？
2. **行业定位 (Context)**：基于你的知识库，指出这篇论文在相关领域（如 NLP, CV, 强化学习等）所处的位置。
3. **结构化输出**：使用 HTML 格式输出，确保在网页上具有极佳的可读性。

# 待处理数据
标题: {self.title}
摘要: {self.summary}
引言: {introduction}
结论: {conclusion}

# 输出要求（HTML 格式）
请包含以下模块：
1. **一、 五秒钟定性 (The 5 Cs)**
   - Category (类别)、Context (背景)、Correctness (正确性/假设)、Contributions (贡献)、Clarity (清晰度)。
2. **二、 核心技术解构**
   - 针对的主要痛点是什么？
   - 提出的创新算法/架构是什么？（请用简洁的逻辑链描述）
   - 所做实验的设置和结果是什么？
3. **三、 批判性思考与搜索建议**
   - **局限性**：作者可能隐藏了哪些限制？
   - **搜索关键词**：如果我想深入研究这个方向，我应该搜索哪些关键词?
   - **同类对比**：这篇论文与该领域目前的最优（SOTA）方法相比，优劣在哪里？

# 注意
请使用专业、干练的中文学术口吻。"""
            
            tldr = llm.generate(
                messages=[
                    {
                        "role": "system",
                        "content": "你是一位资深的人工智能首席科学家，拥有极强的文献综述与批判性思维能力。你的任务是运用 S. Keshav 的“三段式阅读法”逻辑，对以下 LaTeX 格式的论文进行深度解构。",
                    },
                    {"role": "user", "content": prompt},
                ]
            )
            logger.info(f"Generated TLDR for {self.arxiv_id}: {tldr}")
            fenced_contents = re.findall(r"```html\s*(.*?)```", tldr, flags=re.DOTALL | re.IGNORECASE)
            if fenced_contents:
                tldr = fenced_contents[0]
            return tldr
        except Exception as e:
            logger.warning(f"Failed to generate TLDR for {self.arxiv_id} due to API error: {e}")
            # 返回摘要作为后备
            return f"<p>{self.summary}</p>"

    @cached_property
    def affiliations(self) -> Optional[list[str]]:
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