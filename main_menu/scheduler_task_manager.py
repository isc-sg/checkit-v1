from celery import Celery




class CeleryTaskManager:
    def __init__(self):
        self.app = Celery('camera_checker', broker='redis://localhost:6379')  # Update with your project name

    def get_active_tasks(self):
        """
        Provides active tasks currently running in the scheduler.
        
        Parameters:
        - None

        Returns:
        Responses:
        - json containing a list of tasks:
        - tasks contain:
            - id - unique identifier for each task
            - name - name of the method that initiated the task
            - args - arguments passed to the task
                - status of the job submission
                - list of camera_ids e.g. [1274, 1275, 1276]
                - run number e.g. 52
                - user_name that initiated the task e.g. "checkit",
                - internal_id e.g "83024D215FE3EC80B55CBBCF5BD209A0"
            
            - kwargs - typically {}
            - worker - name of the worker e.g. "worker2@checkit"
        
        """
        # app = celery.Celery('camera_checker', broker='redis://localhost:6379')
        inspector = self.app.control.inspect()
        active_tasks = inspector.active()
        
        tasks = []
        if active_tasks:
            for worker, tasks_list in active_tasks.items():
                for task in tasks_list:
                    tasks.append({
                        'id': task['id'],
                        'name': task['name'],
                        'args': task['args'],
                        'kwargs': task['kwargs'],
                        # 'state': task['state'],
                        'worker': worker,
                    })
        return tasks