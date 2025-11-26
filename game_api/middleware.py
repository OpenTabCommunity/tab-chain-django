class SimpleCorsMiddleware:
    """
    Simple CORS middleware to allow cross-origin requests.
    """

    # List of allowed origins
    ALLOWED_ORIGINS = [
        "http://91.206.178.230:3000",  # frontend origin
    ]

    ALLOWED_METHODS = "GET, POST, PUT, DELETE, OPTIONS"
    ALLOWED_HEADERS = "Content-Type, Authorization"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get("Origin")

        # Preflight OPTIONS request
        if request.method == "OPTIONS":
            from django.http import HttpResponse
            response = HttpResponse()
            if origin in self.ALLOWED_ORIGINS:
                response["Access-Control-Allow-Origin"] = origin
                response["Access-Control-Allow-Methods"] = self.ALLOWED_METHODS
                response["Access-Control-Allow-Headers"] = self.ALLOWED_HEADERS
                response["Access-Control-Allow-Credentials"] = "true"
            return response

        # Normal request
        response = self.get_response(request)
        if origin in self.ALLOWED_ORIGINS:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Credentials"] = "true"

        return response
