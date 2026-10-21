from enum import StrEnum


class Permissions(StrEnum):
    ADMIN = "admin"
    ACCOUNTS_READ = "accounts.read"
    ACCOUNTS_CREATE = "accounts.create"
    ACCOUNTS_UPDATE = "accounts.update"
    ACCOUNTS_DELETE = "accounts.delete"
    ROLES_READ = "roles.read"
    ROLES_CREATE = "roles.create"
    ROLES_UPDATE = "roles.update"
    ROLES_DELETE = "roles.delete"
    PROFILE_UPDATE = "profile.update"
    REQUESTS_READ = "requests.read"
    REQUESTS_CREATE = "requests.create"
    REQUESTS_UPDATE = "requests.update"
    REQUESTS_DELETE = "requests.delete"
    CREDITS_READ = "credits.read"
    CREDITS_CREATE = "credits.create"
    CREDITS_UPDATE = "credits.update"
    CREDITS_DELETE = "credits.delete"
