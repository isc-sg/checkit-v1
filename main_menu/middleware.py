from django.shortcuts import render


class ExceptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except Exception as e:
            # Handle the exception and pass its message to 500.html
            return render(request, "500.html", {"error_message": str(e)}, status=500)