from locust import HttpLocust, TaskSet, task
class writeDB(TaskSet):
    @task(2)
    def index(self):
        self.client.get('/')

    @task(1)
    def app(self):
        self.client.get('/app')

class WebsiteUser(HttpLocust):
    task_set = writeDB
    min_wait = 5000
    max_wait = 9000