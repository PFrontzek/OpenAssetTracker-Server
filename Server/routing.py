from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter
from channels.routing import URLRouter

import main.urls

application = ProtocolTypeRouter(
    {
        "websocket": AuthMiddlewareStack(URLRouter(main.urls.websocket_urlpatterns)),
    }
)
