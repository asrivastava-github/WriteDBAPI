from locust import HttpUser, task, between


class QuickstartUser(HttpUser):
    wait_time = between(1, 2.5)

    @task(1)
    def get_app(self):
        self.client.get("/app")

    @task(2)
    def post_app(self):
        self.client.post("/app")
