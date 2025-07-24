import os
import requests
from django.conf import settings
from ratelimit import limits, sleep_and_retry

# 从环境变量获取API密钥和速率限制
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
API_RATE_LIMIT = os.getenv('API_RATE_LIMIT', '10/minute')
RATE_LIMIT_CALLS, RATE_LIMIT_PERIOD = API_RATE_LIMIT.split('/')
RATE_LIMIT_PERIOD = {'minute': 60, 'hour': 3600}[RATE_LIMIT_PERIOD]


class DeepSeekClient:
    API_BASE_URL = "https://api.deepseek.com/v1/chat/completions"

    def __init__(self):
        self.api_key = DEEPSEEK_API_KEY
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY is not set in environment variables")

    @sleep_and_retry
    @limits(calls=int(RATE_LIMIT_CALLS), period=int(RATE_LIMIT_PERIOD))
    def generate_test_cases(self, requirement, user_prompt):
        """
        调用DeepSeek API生成测试用例
        :param requirement: 产品需求
        :param user_prompt: 用户自定义的提示词模板
        :return: 生成的测试用例结构
        """
        # 构建完整提示词
        full_prompt = user_prompt.format(requirement=requirement)

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "你是一位专业的测试工程师，擅长生成全面的测试用例"},
                {"role": "user", "content": full_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 2048
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
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content']
        except requests.exceptions.RequestException as e:
            raise Exception(f"API request failed: {str(e)}")