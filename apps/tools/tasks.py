# tasks.py
@shared_task(bind=True)
def generate_testcases_task(self, requirement, user_id):
    try:
        view = GenerateTestCasesAPI()
        result = view._call_deepseek_api(requirement)
        xmind_path = view._generate_xmind(result)

        TestCaseGeneration.objects.create(
            user_id=user_id,
            requirement=requirement,
            raw_response=result,
            output_file=xmind_path,
            status='SUCCESS'
        )
        return xmind_path
    except Exception as e:
        self.retry(exc=e, countdown=60)