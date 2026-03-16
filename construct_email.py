from paper import ArxivPaper
import math
from tqdm import tqdm
from email.header import Header
from email.mime.text import MIMEText
from email.utils import parseaddr, formataddr
import smtplib
import datetime
from loguru import logger
from concurrent.futures import ThreadPoolExecutor
from typing import Tuple
import threading
import re

framework = """
<!DOCTYPE HTML>
<html>
<head>
  <style>
    .star-wrapper {
      font-size: 1.3em; /* 调整星星大小 */
      line-height: 1; /* 确保垂直对齐 */
      display: inline-flex;
      align-items: center; /* 保持对齐 */
    }
    .half-star {
      display: inline-block;
      width: 0.5em; /* 半颗星的宽度 */
      overflow: hidden;
      white-space: nowrap;
      vertical-align: middle;
    }
    .full-star {
      vertical-align: middle;
    }
  </style>
</head>
<body>

<div>
    __CONTENT__
</div>

<br><br>
<div>
To unsubscribe, remove your email in your Github Action setting.
</div>

</body>
</html>
"""

def get_empty_html():
  block_template = """
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-family: Arial, sans-serif; border: 1px solid #ddd; border-radius: 8px; padding: 16px; background-color: #f9f9f9;">
  <tr>
    <td style="font-size: 20px; font-weight: bold; color: #333;">
        No Papers Today. Take a Rest!
    </td>
  </tr>
  </table>
  """
  return block_template

def get_block_html(title:str, authors:str, rate:str,arxiv_id:str, abstract:str, pdf_url:str, code_url:str=None, affiliations:str=None):
    code = f'<a href="{code_url}" style="display: inline-block; text-decoration: none; font-size: 14px; font-weight: bold; color: #fff; background-color: #5bc0de; padding: 8px 16px; border-radius: 4px; margin-left: 8px;">Code</a>' if code_url else ''
    block_template = """
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-family: Arial, sans-serif; border: 1px solid #ddd; border-radius: 8px; padding: 16px; background-color: #f9f9f9;">
    <tr>
        <td style="font-size: 20px; font-weight: bold; color: #333;">
            {title}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #666; padding: 8px 0;">
            {authors}
            <br>
            <i>{affiliations}</i>
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #333; padding: 8px 0;">
            <strong>Relevance:</strong> {rate}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #333; padding: 8px 0;">
            <strong>arXiv ID:</strong> {arxiv_id}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #333; padding: 8px 0;">
            <strong>TLDR:</strong> {abstract}
        </td>
    </tr>

    <tr>
        <td style="padding: 8px 0;">
            <a href="{pdf_url}" style="display: inline-block; text-decoration: none; font-size: 14px; font-weight: bold; color: #fff; background-color: #d9534f; padding: 8px 16px; border-radius: 4px;">PDF</a>
            {code}
        </td>
    </tr>
</table>
"""
    return block_template.format(title=title, authors=authors,rate=rate,arxiv_id=arxiv_id, abstract=abstract, pdf_url=pdf_url, code=code, affiliations=affiliations)

def get_stars(score:float):
    full_star = '<span class="full-star">⭐</span>'
    half_star = '<span class="half-star">⭐</span>'
    low = 6
    high = 8
    if score <= low:
        return ''
    elif score >= high:
        return full_star * 5
    else:
        interval = (high-low) / 10
        star_num = math.ceil((score-low) / interval)
        full_star_num = int(star_num/2)
        half_star_num = star_num - full_star_num * 2
        return '<div class="star-wrapper">'+full_star * full_star_num + half_star * half_star_num + '</div>'

def process_single_paper(args: Tuple[int, ArxivPaper]) -> Tuple[int, str]:
    idx, p = args
    try:
        rate = get_stars(p.score)
        authors = [a.name for a in p.authors[:5]]

        if len(p.authors) > 8:
            last_authors = [a.name for a in p.authors[-3:]]
            authors += ['...'] + last_authors

        authors = ', '.join(authors)
            
        try:
            if p.affiliations is not None:
                affiliations = p.affiliations[:]
                affiliations = ', '.join(affiliations)
                # if len(p.affiliations) > 5:
                    # affiliations += ', ...'
            else:
                affiliations = 'Unknown Affiliation'
        except Exception as e:
            logger.warning(f"Failed to get affiliations for paper {p.arxiv_id}: {e}")
            affiliations = 'Unknown Affiliation'
        
        try:
            tldr = p.tldr
        except Exception as e:
            logger.warning(f"Failed to get TLDR for paper {p.arxiv_id}: {e}")
            tldr = f"<p>{p.summary}</p>"
        
        html_block = get_block_html(p.title, authors, rate, p.arxiv_id, tldr, p.pdf_url, p.code_url, affiliations)
        return idx, html_block
    except Exception as e:
        logger.error(f"Failed to process paper {p.arxiv_id}: {e}")
        # 返回一个基本的HTML块，即使处理失败也能显示论文基本信息
        try:
            authors = ', '.join([a.name for a in p.authors[:5]])
            if len(p.authors) > 5:
                authors += ', ...'
            html_block = get_block_html(
                p.title, 
                authors, 
                get_stars(p.score) if p.score else '', 
                p.arxiv_id, 
                f"<p>{p.summary}</p>", 
                p.pdf_url, 
                p.code_url, 
                'Unknown Affiliation'
            )
            return idx, html_block
        except Exception as e2:
            logger.error(f"Failed to create fallback HTML for paper {p.arxiv_id}: {e2}")
            # 最后的后备方案：返回一个简单的HTML块
            html_block = f"""
            <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-family: Arial, sans-serif; border: 1px solid #ddd; border-radius: 8px; padding: 16px; background-color: #f9f9f9;">
            <tr>
                <td style="font-size: 20px; font-weight: bold; color: #333;">
                    {p.title}
                </td>
            </tr>
            <tr>
                <td style="font-size: 14px; color: #666; padding: 8px 0;">
                    <strong>arXiv ID:</strong> {p.arxiv_id}
                </td>
            </tr>
            <tr>
                <td style="padding: 8px 0;">
                    <a href="{p.pdf_url}" style="display: inline-block; text-decoration: none; font-size: 14px; font-weight: bold; color: #fff; background-color: #d9534f; padding: 8px 16px; border-radius: 4px;">PDF</a>
                </td>
            </tr>
            </table>
            """
            return idx, html_block

def render_email(papers: list[ArxivPaper]):
    if len(papers) == 0:
        return framework.replace('__CONTENT__', get_empty_html())
    
    # 创建进度条
    pbar = tqdm(total=len(papers), desc='Rendering Email')
    # 用于在回调函数中更新进度条
    pbar_lock = threading.Lock()
    
    def update_pbar(*args):
        with pbar_lock:
            pbar.update(1)
    
    # 创建线程池
    with ThreadPoolExecutor(max_workers=min(10, len(papers))) as executor:
        # 提交所有任务并保存future对象
        future_to_idx = {
            executor.submit(process_single_paper, (idx, paper)): idx 
            for idx, paper in enumerate(papers)
        }
        
        # 为每个future添加回调来更新进度条
        for future in future_to_idx:
            future.add_done_callback(update_pbar)
        
        # 收集所有结果，即使部分失败也继续处理
        results = []
        failed_count = 0
        for future in future_to_idx:
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                failed_count += 1
                idx = future_to_idx[future]
                logger.error(f"Failed to process paper at index {idx}: {e}")
                # 不添加失败的结果，这样失败的论文就不会出现在邮件中
        
        if failed_count > 0:
            logger.warning(f"Failed to process {failed_count} paper(s), but continuing with {len(results)} successful ones.")
    
    pbar.close()
    
    # 如果所有论文都处理失败，返回空邮件
    if len(results) == 0:
        logger.warning("All papers failed to process, returning empty email.")
        return framework.replace('__CONTENT__', get_empty_html())
    
    # 按原始顺序排序结果
    results.sort(key=lambda x: x[0])
    # 提取HTML块
    html_blocks = [r[1] for r in results]

    content = '<br>' + '</br><br>'.join(html_blocks) + '</br>'
    return framework.replace('__CONTENT__', content)

def send_email(sender:str, receiver:str, password:str, smtp_server:str, smtp_port:int, html:str):
    def _format_addr(s):
        name, addr = parseaddr(s)
        return formataddr((Header(name, 'utf-8').encode(), addr))

    msg = MIMEText(html, 'html', 'utf-8')
    msg['From'] = _format_addr('Github Action <%s>' % sender)
    msg['To'] = _format_addr('You <%s>' % receiver)
    today = datetime.datetime.now().strftime('%Y/%m/%d')
    msg['Subject'] = Header(f'Daily arXiv {today}', 'utf-8').encode()

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
    except Exception as e:
        logger.warning(f"Failed to use TLS. {e}")
        logger.warning(f"Try to use SSL.")
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)

    server.login(sender, password)
    server.sendmail(sender, [receiver], msg.as_string())
    server.quit()
