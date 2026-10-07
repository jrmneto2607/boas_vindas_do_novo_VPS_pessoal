import hashlib
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from .models import RequestBucket


class ParticipationRateLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view, args, kwargs):
        name = request.resolver_match.url_name
        rule = settings.RATE_LIMITS.get(name)
        if request.method != "POST" or not rule:
            return None
        limit, seconds = rule
        remote = request.META.get("REMOTE_ADDR", "unknown")
        if remote in settings.RATE_LIMIT_TRUSTED_PROXIES:
            import ipaddress
            try:
                remote = str(ipaddress.ip_address(request.META.get("HTTP_X_REAL_IP", remote)))
            except ValueError:
                pass
        identities = ["ip:" + remote]
        value = request.POST.get("username") or request.POST.get("email")
        if value:
            identities.append("account:" + value.strip().lower())
        if request.user.is_authenticated:
            identities.append("user:" + str(request.user.pk))
        now = timezone.now()
        for identity in identities:
            key = hashlib.sha256((name + ":" + identity).encode()).hexdigest()
            with transaction.atomic():
                RequestBucket.objects.get_or_create(key=key, defaults={"expires_at": now + timedelta(seconds=seconds)})
                bucket = RequestBucket.objects.select_for_update().get(pk=key)
                if bucket.expires_at <= now:
                    bucket.count, bucket.expires_at = 0, now + timedelta(seconds=seconds)
                if bucket.count >= limit:
                    response = HttpResponse("Muitas tentativas. Aguarde alguns minutos antes de tentar novamente.", status=429, content_type="text/plain; charset=utf-8")
                    response["Retry-After"] = str(max(1, int((bucket.expires_at-now).total_seconds())))
                    return response
                bucket.count += 1
                bucket.save(update_fields=["count", "expires_at"])
        return None
