# web/config/middleware.py

class DisableCSRFMiddleware:
    """
    Отключает CSRF только для API-роутов (/api/*).
    Для обычных HTML-страниц CSRF остаётся включённым.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/api/"):
            setattr(request, "_dont_enforce_csrf_checks", True)
        return self.get_response(request)