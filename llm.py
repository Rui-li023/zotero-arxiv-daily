import time
import random
from openai import OpenAI
from openai import OpenAIError, APITimeoutError
from loguru import logger

GLOBAL_LLM = None

class LLM:
    def __init__(self, api_key: str = None, base_url: str = None, model: str = None,lang: str = "English"):
        if api_key:
            self.llm = OpenAI(api_key=api_key, base_url=base_url)
        else:
            self.llm = Llama.from_pretrained(
                repo_id="Qwen/Qwen2.5-3B-Instruct-GGUF",
                filename="qwen2.5-3b-instruct-q4_k_m.gguf",
                n_ctx=5_000,
                n_threads=4,
                verbose=False,
            )
        self.model = model
        self.lang = lang

    def generate(self, messages: list[dict]) -> str:
        max_retries = 5
        base_delay = 1  # 初始延迟1秒
        
        for attempt in range(max_retries):
            try:
                if isinstance(self.llm, OpenAI):
                    response = self.llm.chat.completions.create(
                        messages=messages,
                        temperature=0,
                        model=self.model,
                        extra_body={"keep_alive": "10m"}
                    )
                    return response.choices[0].message.content
                else:
                    response = self.llm.create_chat_completion(
                        messages=messages,
                        temperature=0
                    )
                    return response["choices"][0]["message"]["content"]
                    
            except (OpenAIError, Exception) as e:
                if attempt == max_retries - 1:
                    logger.error(f"Maximum retries reached. Last error: {str(e)}")
                    raise
                
                # 计算指数退避延迟时间
                delay = (2 ** attempt * base_delay + 
                        random.uniform(0, 0.1 * (2 ** attempt)))
                
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries} failed. "
                    f"Retrying in {delay:.2f} seconds. Error: {str(e)}"
                )
                
                time.sleep(delay)

    def generate_stream(self, messages: list[dict]):
        """Yield tokens one by one using streaming. Only works with OpenAI-compatible API."""
        if not isinstance(self.llm, OpenAI):
            yield self.generate(messages)
            return

        max_retries = 3
        base_delay = 1
        for attempt in range(max_retries):
            try:
                stream = self.llm.chat.completions.create(
                    messages=messages,
                    temperature=0,
                    model=self.model,
                    stream=True,
                )
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                return
            except (OpenAIError, Exception) as e:
                if attempt == max_retries - 1:
                    logger.error(f"Stream max retries reached: {e}")
                    raise
                delay = 2 ** attempt * base_delay + random.uniform(0, 0.1 * (2 ** attempt))
                logger.warning(f"Stream attempt {attempt + 1}/{max_retries} failed: {e}. Retrying in {delay:.2f}s")
                time.sleep(delay)


def set_global_llm(api_key: str = None, base_url: str = None, model: str = None, lang: str = "English"):
    global GLOBAL_LLM
    GLOBAL_LLM = LLM(api_key=api_key, base_url=base_url, model=model, lang=lang)

def get_llm() -> LLM:
    if GLOBAL_LLM is None:
        logger.info("No global LLM found, creating a default one. Use `set_global_llm` to set a custom one.")
        set_global_llm()
    return GLOBAL_LLM