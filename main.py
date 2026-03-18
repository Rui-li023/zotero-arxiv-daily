import arxiv
import argparse
import datetime
import os
import sys
from dotenv import load_dotenv
load_dotenv(override=True)
os.environ["TOKENIZERS_PARALLELISM"] = "false"
from pyzotero import zotero
from recommender import rerank_paper
from construct_email import render_email, send_email
from storage import save_daily_papers, load_paper_history, update_paper_history
from tqdm import trange,tqdm
from loguru import logger
from gitignore_parser import parse_gitignore
from tempfile import mkstemp
from paper import ArxivPaper
from llm import set_global_llm
import feedparser

def get_zotero_corpus(id:str,key:str) -> list[dict]:
    zot = zotero.Zotero(id, 'user', key)
    collections = zot.everything(zot.collections())
    collections = {c['key']:c for c in collections}
    corpus = zot.everything(zot.items(itemType='conferencePaper || journalArticle || preprint'))
    corpus = [c for c in corpus if c['data']['abstractNote'] != '']
    def get_collection_path(col_key:str) -> str:
        if p := collections[col_key]['data']['parentCollection']:
            return get_collection_path(p) + '/' + collections[col_key]['data']['name']
        else:
            return collections[col_key]['data']['name']
    for c in corpus:
        paths = [get_collection_path(col) for col in c['data']['collections']]
        c['paths'] = paths
    return corpus

def filter_corpus(corpus:list[dict], pattern:str) -> list[dict]:
    _,filename = mkstemp()
    with open(filename,'w') as file:
        file.write(pattern)
    matcher = parse_gitignore(filename,base_dir='./')
    new_corpus = []
    for c in corpus:
        match_results = [matcher(p) for p in c['paths']]
        if not any(match_results):
            new_corpus.append(c)
    os.remove(filename)
    return new_corpus


def apply_subscription_boosts(papers, subscriptions: list[dict]):
    """Apply keyword subscription boosts to paper scores.
    Each subscription: {keyword, weight, enabled}.
    If a paper's title+abstract contains the keyword, score *= (1 + 0.1 * weight).
    Then re-sort by score descending.
    """
    active = [s for s in subscriptions if s.get("enabled", True)]
    if not active:
        return papers
    for p in papers:
        text = (p.title + " " + p.summary).lower() if hasattr(p, 'title') else ""
        for sub in active:
            kw = sub.get("keyword", "").lower()
            weight = sub.get("weight", 1)
            if kw and kw in text:
                if p.score is not None:
                    p.score *= (1 + 0.1 * weight)
    papers.sort(key=lambda p: p.score if p.score is not None else 0, reverse=True)
    return papers


def get_arxiv_paper(query:str, debug:bool=False) -> list[ArxivPaper]:
    client = arxiv.Client(num_retries=10,delay_seconds=10)
    # Strip "cat:" prefix from each category for RSS URL (e.g. "cat:cs.AI+cs.CV" -> "cs.AI+cs.CV")
    rss_query = '+'.join(c.removeprefix('cat:') for c in query.split('+'))
    feed = feedparser.parse(f"https://rss.arxiv.org/atom/{rss_query}")
    if 'Feed error for query' in feed.feed.title:
        raise Exception(f"Invalid ARXIV_QUERY: {query}.")
    if not debug:
        papers = []
        all_paper_ids = [i.id.removeprefix("oai:arXiv.org:") for i in feed.entries if i.arxiv_announce_type == 'new']
        bar = tqdm(total=len(all_paper_ids),desc="Retrieving Arxiv papers")
        for i in range(0,len(all_paper_ids),50):
            search = arxiv.Search(id_list=all_paper_ids[i:i+50])
            batch = [ArxivPaper(p) for p in client.results(search)]
            bar.update(len(batch))
            papers.extend(batch)
        bar.close()

    else:
        logger.debug("Retrieve 5 arxiv papers regardless of the date.")
        search = arxiv.Search(query='cat:cs.AI', sort_by=arxiv.SortCriterion.SubmittedDate)
        papers = []
        for i in client.results(search):
            papers.append(ArxivPaper(i))
            if len(papers) == 5:
                break

    return papers



parser = argparse.ArgumentParser(description='Recommender system for academic papers')

def add_argument(*args, **kwargs):
    def get_env(key:str,default=None):
        # handle environment variables generated at Workflow runtime
        # Unset environment variables are passed as '', we should treat them as None
        v = os.environ.get(key)
        if v == '' or v is None:
            return default
        return v
    parser.add_argument(*args, **kwargs)
    arg_full_name = kwargs.get('dest',args[-1][2:])
    env_name = arg_full_name.upper()
    env_value = get_env(env_name)
    if env_value is not None:
        #convert env_value to the specified type
        if kwargs.get('type') == bool:
            env_value = env_value.lower() in ['true','1']
        else:
            env_value = kwargs.get('type')(env_value)
        parser.set_defaults(**{arg_full_name:env_value})


if __name__ == '__main__':
    
    add_argument('--zotero_id', type=str, help='Zotero user ID')
    add_argument('--zotero_key', type=str, help='Zotero API key')
    add_argument('--zotero_ignore',type=str,help='Zotero collection to ignore, using gitignore-style pattern.')
    add_argument('--send_empty', type=bool, help='If get no arxiv paper, send empty email',default=False)
    add_argument('--max_paper_num', type=int, help='Maximum number of papers to recommend',default=25)
    add_argument('--arxiv_query', type=str, help='Arxiv search query')
    add_argument('--smtp_server', type=str, help='SMTP server')
    add_argument('--smtp_port', type=int, help='SMTP port')
    add_argument('--sender', type=str, help='Sender email address')
    add_argument('--receiver', type=str, help='Receiver email address')
    add_argument('--sender_password', type=str, help='Sender email password')
    add_argument(
        "--use_llm_api",
        type=bool,
        help="Use OpenAI API to generate TLDR",
        default=False,
    )
    add_argument(
        "--openai_api_key",
        type=str,
        help="OpenAI API key",
        default=None,
    )
    add_argument(
        "--openai_api_base",
        type=str,
        help="OpenAI API base URL",
        default="https://api.openai.com/v1",
    )
    add_argument(
        "--model_name",
        type=str,
        help="LLM Model Name",
        default="gpt-4o",
    )
    add_argument(
        "--language",
        type=str,
        help="Language of TLDR",
        default="English",
    )
    parser.add_argument('--debug', action='store_true', help='Debug mode')
    parser.add_argument('--web_only', action='store_true', help='Only fetch papers and save JSON for the web interface (skip Zotero reranking and email)')
    args = parser.parse_args()

    if args.debug:
        logger.remove()
        logger.add(sys.stdout, level="DEBUG")
        logger.debug("Debug mode is on.")
    else:
        logger.remove()
        logger.add(sys.stdout, level="INFO")

    if args.web_only:
        # Simplified mode: fetch papers, generate LLM analysis, save JSON only
        assert args.arxiv_query or args.debug, "Must provide --arxiv_query or --debug for --web_only mode"
        if args.use_llm_api:
            assert args.openai_api_key is not None
            set_global_llm(api_key=args.openai_api_key, base_url=args.openai_api_base, model=args.model_name, lang=args.language)
        else:
            set_global_llm(lang=args.language)

        logger.info("Retrieving Arxiv papers...")
        papers = get_arxiv_paper(args.arxiv_query or 'cat:cs.AI', args.debug)
        if len(papers) == 0:
            logger.info("No new papers found.")
            exit(0)

        # Deduplicate against history
        history = load_paper_history()
        before = len(papers)
        papers = [p for p in papers if p.arxiv_id not in history]
        if before != len(papers):
            logger.info(f"Filtered {before - len(papers)} duplicate papers.")
        if not papers:
            logger.info("All papers were duplicates.")
            exit(0)

        # Rerank using Zotero if credentials are available
        if args.zotero_id and args.zotero_key:
            logger.info("Retrieving Zotero corpus for reranking...")
            corpus = get_zotero_corpus(args.zotero_id, args.zotero_key)
            logger.info(f"Retrieved {len(corpus)} papers from Zotero.")
            if args.zotero_ignore:
                corpus = filter_corpus(corpus, args.zotero_ignore)
                logger.info(f"Remaining {len(corpus)} papers after filtering.")
            if corpus:
                papers = rerank_paper(papers, corpus)
                logger.info("Papers reranked by Zotero similarity.")
            else:
                logger.warning("Zotero corpus is empty. Using default ordering.")
                for i, p in enumerate(papers):
                    p.score = max(10 - i * 0.3, 5)
        else:
            logger.warning("Zotero credentials not provided for --web_only mode. Papers will not be ranked by research interest.")
            for i, p in enumerate(papers):
                p.score = max(10 - i * 0.3, 5)

        if args.max_paper_num != -1:
            papers = papers[:args.max_paper_num]

        logger.info(f"Processing {len(papers)} papers for web...")
        html = render_email(papers)  # This triggers highlight/tldr/affiliations computation

        today = datetime.datetime.now().strftime('%Y-%m-%d')
        save_daily_papers(papers, today)
        update_paper_history(papers, today)
        logger.success(f"Saved {len(papers)} papers to data/{today}.json")
    else:
        # Full pipeline: Zotero + rerank + email + save
        assert (
            not args.use_llm_api or args.openai_api_key is not None
        )  # If use_llm_api is True, openai_api_key must be provided

        logger.info("Retrieving Zotero corpus...")
        corpus = get_zotero_corpus(args.zotero_id, args.zotero_key)
        logger.info(f"Retrieved {len(corpus)} papers from Zotero.")
        if args.zotero_ignore:
            logger.info(f"Ignoring papers in:\n {args.zotero_ignore}...")
            corpus = filter_corpus(corpus, args.zotero_ignore)
            logger.info(f"Remaining {len(corpus)} papers after filtering.")
        logger.info("Retrieving Arxiv papers...")
        papers = get_arxiv_paper(args.arxiv_query, args.debug)

        # Deduplicate against history
        history = load_paper_history()
        before = len(papers)
        papers = [p for p in papers if p.arxiv_id not in history]
        if before != len(papers):
            logger.info(f"Filtered {before - len(papers)} duplicate papers.")

        if len(papers) == 0:
            logger.info("No new papers found. Yesterday maybe a holiday and no one submit their work :). If this is not the case, please check the ARXIV_QUERY.")
            if not args.send_empty:
              exit(0)
        else:
            logger.info("Reranking papers...")
            papers = rerank_paper(papers, corpus)
            if args.max_paper_num != -1:
                papers = papers[:args.max_paper_num]
            if args.use_llm_api:
                logger.info("Using OpenAI API as global LLM.")
                set_global_llm(api_key=args.openai_api_key, base_url=args.openai_api_base, model=args.model_name, lang=args.language)
            else:
                logger.info("Using Local LLM as global LLM.")
                set_global_llm(lang=args.language)

        html = render_email(papers)

        # Save papers to JSON for the web interface
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        save_daily_papers(papers, today)
        update_paper_history(papers, today)

        logger.info("Sending email...")
        send_email(args.sender, args.receiver, args.sender_password, args.smtp_server, args.smtp_port, html)
        logger.success("Email sent successfully! If you don't receive the email, please check the configuration and the junk box.")

