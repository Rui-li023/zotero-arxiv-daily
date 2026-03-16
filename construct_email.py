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
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      background-color: #f5f7fa;
      margin: 0;
      padding: 20px;
      color: #2c3e50;
      line-height: 1.6;
    }
    
    .container {
      max-width: 800px;
      margin: 0 auto;
      background-color: #ffffff;
      border-radius: 12px;
      box-shadow: 0 2px 12px rgba(0,0,0,0.08);
      overflow: hidden;
    }
    
    .header {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      padding: 32px 24px;
      text-align: center;
    }
    
    .header h1 {
      margin: 0;
      font-size: 28px;
      font-weight: 600;
    }
    
    .header .subtitle {
      margin-top: 8px;
      font-size: 16px;
      opacity: 0.95;
    }
    
    .content {
      padding: 24px;
    }
    
    .paper-card {
      background: #ffffff;
      border: 1px solid #e8ecf1;
      border-radius: 8px;
      margin-bottom: 20px;
      overflow: hidden;
      transition: box-shadow 0.2s;
    }
    
    .paper-card:hover {
      box-shadow: 0 4px 12px rgba(0,0,0,0.1);
    }
    
    details {
      border: none;
    }
    
    summary {
      padding: 20px;
      cursor: pointer;
      position: relative;
      list-style: none;
      outline: none;
    }
    
    summary::-webkit-details-marker {
      display: none;
    }
    
    summary::marker {
      display: none;
    }
    
    .paper-title {
      font-size: 18px;
      font-weight: 600;
      color: #2c3e50;
      margin: 0 0 12px 0;
      line-height: 1.4;
    }
    
    .paper-meta {
      font-size: 14px;
      color: #64748b;
      margin-bottom: 8px;
    }
    
    .paper-meta .authors {
      margin-bottom: 4px;
    }
    
    .paper-meta .affiliation {
      font-style: italic;
      color: #94a3b8;
    }
    
    .paper-highlight {
      font-size: 14px;
      color: #475569;
      background-color: #f8fafc;
      padding: 12px;
      border-left: 3px solid #667eea;
      margin: 12px 0;
      border-radius: 4px;
    }
    
    .paper-info {
      display: flex;
      align-items: center;
      gap: 16px;
      margin-top: 12px;
      flex-wrap: wrap;
    }
    
    .star-wrapper {
      font-size: 1.1em;
      line-height: 1;
      display: inline-flex;
      align-items: center;
    }
    
    .half-star {
      display: inline-block;
      width: 0.5em;
      overflow: hidden;
      white-space: nowrap;
      vertical-align: middle;
    }
    
    .full-star {
      vertical-align: middle;
    }
    
    .arxiv-id {
      font-family: 'Courier New', monospace;
      font-size: 13px;
      color: #64748b;
      background-color: #f1f5f9;
      padding: 4px 8px;
      border-radius: 4px;
    }
    
    .expand-indicator {
      color: #667eea;
      font-size: 12px;
      font-weight: 500;
      margin-top: 8px;
      user-select: none;
    }
    
    .expand-indicator::before {
      content: '▼ ';
      font-size: 10px;
    }
    
    details[open] .expand-indicator::before {
      content: '▲ ';
    }
    
    .paper-details {
      padding: 0 20px 20px 20px;
      border-top: 1px solid #e8ecf1;
      background-color: #fafbfc;
    }
    
    .paper-analysis {
      padding-top: 16px;
    }
    
    .paper-analysis .section {
      margin-bottom: 20px;
    }
    
    .paper-analysis h3 {
      font-size: 16px;
      color: #667eea;
      margin: 0 0 8px 0;
      font-weight: 600;
    }
    
    .paper-analysis p {
      margin: 0;
      font-size: 14px;
      color: #475569;
      line-height: 1.6;
    }
    
    .paper-analysis ul {
      margin: 8px 0;
      padding-left: 20px;
    }
    
    .paper-analysis li {
      margin-bottom: 8px;
      font-size: 14px;
      color: #475569;
      line-height: 1.6;
    }

    .paper-actions {
      margin-top: 16px;
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }
    
    .btn {
      display: inline-block;
      text-decoration: none;
      font-size: 14px;
      font-weight: 500;
      padding: 10px 20px;
      border-radius: 6px;
      transition: all 0.2s;
    }
    
    .btn-pdf {
      color: #ffffff;
      background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
    }
    
    .btn-pdf:hover {
      box-shadow: 0 4px 12px rgba(245, 87, 108, 0.4);
      transform: translateY(-2px);
    }
    
    .btn-code {
      color: #ffffff;
      background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
    }
    
    .btn-code:hover {
      box-shadow: 0 4px 12px rgba(79, 172, 254, 0.4);
      transform: translateY(-2px);
    }
    
    .footer {
      text-align: center;
      padding: 24px;
      color: #94a3b8;
      font-size: 14px;
      background-color: #f8fafc;
      border-top: 1px solid #e8ecf1;
    }
    
    .empty-state {
      text-align: center;
      padding: 60px 24px;
      color: #64748b;
    }
    
    .empty-state h2 {
      font-size: 24px;
      margin: 0;
      color: #2c3e50;
    }
  </style>
</head>
<body>

<div class="container">
  __HEADER__
  <div class="content">
    __CONTENT__
  </div>
  <div class="footer">
    Generated by arXiv Daily Alert | To unsubscribe, remove your email in Github Action settings
  </div>
</div>

</body>
</html>
"""

def get_header_html(paper_count: int, date: str):
    return f"""
  <div class="header">
    <h1>arXiv Daily Papers</h1>
    <div class="subtitle">{date} | {paper_count} papers</div>
  </div>
"""

def get_empty_html():
    return """
  <div class="empty-state">
    <h2>No Papers Today</h2>
    <p>Take a rest and enjoy your day!</p>
  </div>
"""

def get_block_html(idx: int, title: str, authors: str, rate: str, arxiv_id: str, 
                   highlight: str, details: str, pdf_url: str, code_url: str = None, 
                   affiliations: str = None):
    code_button = f'<a href="{code_url}" class="btn btn-code">View Code</a>' if code_url else ''
    affiliation_html = f'<div class="affiliation">{affiliations}</div>' if affiliations else ''
    stars_html = f'<div class="stars">{rate}</div>' if rate else ''
    
    return f"""
    <div class="paper-card">
      <details>
        <summary>
          <h2 class="paper-title">{title}</h2>
          <div class="paper-meta">
            <div class="authors">{authors}</div>
            {affiliation_html}
          </div>
          <div class="paper-highlight">{highlight}</div>
          <div class="paper-info">
            {stars_html}
            <span class="arxiv-id">{arxiv_id}</span>
          </div>
          <div class="expand-indicator">展开详细分析</div>
        </summary>
        <div class="paper-details">
          {details}
          <div class="paper-actions">
            <a href="{pdf_url}" class="btn btn-pdf">View PDF</a>
            {code_button}
          </div>
        </div>
      </details>
    </div>
"""

def get_stars(score: float):
    full_star = '<span class="full-star">⭐</span>'
    half_star = '<span class="half-star">⭐</span>'
    low = 6
    high = 8
    if score <= low:
        return ''
    elif score >= high:
        return full_star * 5
    else:
        interval = (high - low) / 10
        star_num = math.ceil((score - low) / interval)
        full_star_num = int(star_num / 2)
        half_star_num = star_num - full_star_num * 2
        return '<div class="star-wrapper">' + full_star * full_star_num + half_star * half_star_num + '</div>'

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
            else:
                affiliations = None
        except Exception as e:
            logger.warning(f"Failed to get affiliations for paper {p.arxiv_id}: {e}")
            affiliations = None
        
        try:
            highlight = p.highlight
        except Exception as e:
            logger.warning(f"Failed to get highlight for paper {p.arxiv_id}: {e}")
            highlight = "核心创新点暂时无法生成"
        
        try:
            details = p.tldr
        except Exception as e:
            logger.warning(f"Failed to get TLDR for paper {p.arxiv_id}: {e}")
            details = f'<div class="paper-analysis"><div class="section"><p>{p.summary}</p></div></div>'
        
        html_block = get_block_html(idx, p.title, authors, rate, p.arxiv_id, 
                                    highlight, details, p.pdf_url, p.code_url, affiliations)
        return idx, html_block
    except Exception as e:
        logger.error(f"Failed to process paper {p.arxiv_id}: {e}")
        # 返回一个基本的HTML块，即使处理失败也能显示论文基本信息
        try:
            authors = ', '.join([a.name for a in p.authors[:5]])
            if len(p.authors) > 5:
                authors += ', ...'
            html_block = get_block_html(
                idx,
                p.title, 
                authors, 
                get_stars(p.score) if p.score else '', 
                p.arxiv_id,
                "论文概要暂时无法生成",
                f'<div class="paper-analysis"><div class="section"><p>{p.summary}</p></div></div>',
                p.pdf_url, 
                p.code_url,
                None
            )
            return idx, html_block
        except Exception as e2:
            logger.error(f"Failed to create fallback HTML for paper {p.arxiv_id}: {e2}")
            # 最后的后备方案：返回一个简单的HTML块
            html_block = f"""
            <div class="paper-card">
              <div class="paper-summary">
                <h2 class="paper-title">{p.title}</h2>
                <div class="paper-info">
                  <span class="arxiv-id">{p.arxiv_id}</span>
                </div>
                <div class="paper-actions">
                  <a href="{p.pdf_url}" class="btn btn-pdf">View PDF</a>
                </div>
              </div>
            </div>
            """
            return idx, html_block

def render_email(papers: list[ArxivPaper]):
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    
    if len(papers) == 0:
        header = get_header_html(0, today)
        content = get_empty_html()
        return framework.replace('__HEADER__', header).replace('__CONTENT__', content)
    
    # 创建进度条
    pbar = tqdm(total=len(papers), desc='Rendering Email')
    # 用于在回调函数中更新进度条
    pbar_lock = threading.Lock()
    
    def update_pbar(*args):
        with pbar_lock:
            pbar.update(1)
    
    # 创建线程池
    with ThreadPoolExecutor(max_workers=min(20, len(papers))) as executor:
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
        header = get_header_html(0, today)
        content = get_empty_html()
        return framework.replace('__HEADER__', header).replace('__CONTENT__', content)
    
    # 按原始顺序排序结果
    results.sort(key=lambda x: x[0])
    # 提取HTML块
    html_blocks = [r[1] for r in results]

    header = get_header_html(len(results), today)
    content = '\n'.join(html_blocks)
    return framework.replace('__HEADER__', header).replace('__CONTENT__', content)

def send_email(sender: str, receiver: str, password: str, smtp_server: str, smtp_port: int, html: str):
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
