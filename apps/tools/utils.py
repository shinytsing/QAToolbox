import os
import requests
from ratelimit import limits, sleep_and_retry
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from ratelimit import limits, sleep_and_retry
# 替换为 django-ratelimit 的装饰器
from django_ratelimit.decorators import ratelimit  # 新增导入

# 从环境变量获取配置
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
API_RATE_LIMIT = os.getenv('API_RATE_LIMIT', '10/minute')

# 解析速率限制配置
try:
    RATE_LIMIT_CALLS, RATE_LIMIT_PERIOD = API_RATE_LIMIT.split('/')
    RATE_LIMIT_PERIOD = {'minute': 60, 'hour': 3600}[RATE_LIMIT_PERIOD.lower()]
except (ValueError, KeyError):
    RATE_LIMIT_CALLS = 10
    RATE_LIMIT_PERIOD = 60


class DeepSeekClient:
    API_BASE_URL = "https://api.deepseek.com/v1/chat/completions"
    TIMEOUT = 60  # 超时时间（秒）

    def __init__(self):
        self.api_key = DEEPSEEK_API_KEY
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY 未在环境变量中设置，请检查 .env.py 文件")

    @sleep_and_retry
    @limits(calls=int(RATE_LIMIT_CALLS), period=int(RATE_LIMIT_PERIOD))
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError))
    )
    def generate_test_cases(self, requirement: str, user_prompt: str) -> str:
        if not requirement or not user_prompt:
            raise ValueError("需求内容和提示词模板不能为空")

        # 构建完整提示词（要求输出Markdown格式，方便解析为XMind结构）
        full_prompt = user_prompt.format(
            requirement=requirement,
            format="请使用Markdown格式输出：# 场景名称 作为一级标题，- 测试用例 作为列表项"
        )

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "你是专业测试工程师，生成测试用例时需包含场景和具体用例，用Markdown格式输出"},
                {"role": "user", "content": full_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 2048,
            "stream": False
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        try:
            response = requests.post(
                self.API_BASE_URL,
                json=payload,
                headers=headers,
                timeout=self.TIMEOUT
            )
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content']
        except requests.exceptions.RequestException as e:
            error_detail = f"状态码: {response.status_code}" if 'response' in locals() else "无状态码"
            raise Exception(f"API请求失败: {str(e)} ({error_detail})")





# 新增：针对视图的用户级限频装饰器（1分钟最多3次请求）
def user_ratelimit(view_func):
    @ratelimit(key='user', rate='3/m', method='POST', block=True)
    def wrapper(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)
    return wrapper