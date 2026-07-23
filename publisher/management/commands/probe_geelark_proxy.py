"""Read-only GeeLark proxy diagnostic for one cloud-phone profile."""

from __future__ import annotations

import uuid

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from publisher.models import PublicationTask


GEELARK_API = "https://openapi.geelark.com/open/v1"


def masked(value: str) -> str:
    """Return a safe, recognizable form of a secret without exposing it."""
    value = str(value or "")
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * max(4, len(value) - 4)}{value[-2:]}"


class Command(BaseCommand):
    help = (
        "Safely shows the GeeLark proxy linked to one phone number and checks it. "
        "It never changes a proxy or retries a task."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--phone-number",
            required=True,
            help="Phone number from the Publisher table, for example 27.",
        )

    def _post(self, path: str, payload: dict) -> dict:
        token = settings.GEELARK_TOKEN
        if not token:
            raise CommandError("GEELARK_TOKEN is not configured on the server.")

        response = requests.post(
            f"{GEELARK_API}{path}",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "traceId": str(uuid.uuid4()).upper(),
            },
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
        if result.get("code") != 0:
            raise CommandError(
                f"GeeLark API returned {result.get('code')}: "
                f"{result.get('msg') or 'unknown error'}"
            )
        return result.get("data") or {}

    def handle(self, *args, **options):
        phone_number = str(options["phone_number"]).strip()
        task = (
            PublicationTask.objects.filter(profile_number=phone_number)
            .exclude(profile_id="")
            .order_by("-created_at")
            .first()
        )
        if not task:
            raise CommandError(
                f"No Publisher task was found for phone №{phone_number}. "
                "No changes were made."
            )

        phones = self._post("/phone/list", {"ids": [str(task.profile_id)]})
        items = phones.get("items") or []
        if not items:
            raise CommandError(
                f"GeeLark cloud phone {task.profile_id} was not found. No changes were made."
            )

        phone = items[0]
        phone_proxy = phone.get("proxy") or {}
        if not phone_proxy.get("server") or not phone_proxy.get("port"):
            raise CommandError(
                f"GeeLark phone №{phone_number} has no configured proxy. No changes were made."
            )

        proxies = self._post("/proxy/list", {"page": 1, "pageSize": 100}).get("list") or []
        expected = {
            "scheme": str(phone_proxy.get("type") or "").lower(),
            "server": str(phone_proxy.get("server") or ""),
            "port": int(phone_proxy.get("port")),
            "username": str(phone_proxy.get("username") or ""),
        }
        matches = [
            proxy
            for proxy in proxies
            if str(proxy.get("scheme") or "").lower() == expected["scheme"]
            and str(proxy.get("server") or "") == expected["server"]
            and int(proxy.get("port") or 0) == expected["port"]
            and str(proxy.get("username") or "") == expected["username"]
        ]

        self.stdout.write(self.style.SUCCESS("Read-only GeeLark proxy diagnostic"))
        self.stdout.write(f"Phone: №{phone_number}")
        self.stdout.write(f"GeeLark cloud phone ID: {phone.get('id') or task.profile_id}")
        self.stdout.write(f"Proxy: {expected['scheme']}://{expected['server']}:{expected['port']}")
        self.stdout.write(f"Proxy login: {masked(expected['username'])}")

        if len(matches) != 1:
            self.stdout.write(
                self.style.WARNING(
                    "Saved GeeLark proxy could not be matched uniquely; "
                    "the port was NOT changed."
                )
            )
            return

        saved_proxy = matches[0]
        self.stdout.write(f"Saved GeeLark proxy ID: {saved_proxy.get('id')}")

        check = self._post(
            "/proxy/check",
            {
                "proxyQueryChannel": "IP2Location",
                "proxyType": expected["scheme"],
                "server": expected["server"],
                "port": expected["port"],
                "username": phone_proxy.get("username") or "",
                "password": phone_proxy.get("password") or "",
            },
        )
        if check.get("detectStatus"):
            self.stdout.write(self.style.SUCCESS("Proxy check: passed"))
            self.stdout.write(f"Outbound IP: {check.get('outboundIP') or 'not returned'}")
            location = ", ".join(
                part for part in [check.get("countryName"), check.get("city")] if part
            )
            if location:
                self.stdout.write(f"Location: {location}")
        else:
            self.stdout.write(self.style.WARNING("Proxy check: failed"))
            self.stdout.write(f"Reason: {check.get('message') or 'not returned'}")

        self.stdout.write(self.style.SUCCESS("Diagnostic complete. No proxy settings were changed."))
