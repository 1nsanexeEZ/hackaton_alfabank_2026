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
    # Credit applications (module `applications`). Clients get them with the
    # `org_member` policy, underwriters without policies.
    REQUESTS_READ = "requests.read"
    REQUESTS_CREATE = "requests.create"
    REQUESTS_UPDATE = "requests.update"
    REQUESTS_DELETE = "requests.delete"
    # Credit products (module `products`).
    CREDITS_READ = "credits.read"
    CREDITS_CREATE = "credits.create"
    CREDITS_UPDATE = "credits.update"
    CREDITS_DELETE = "credits.delete"
    # Client organizations (module `clients`).
    ORGANIZATIONS_READ = "organizations.read"
    ORGANIZATIONS_UPDATE = "organizations.update"
    # Underwriter tasks (module `process`).
    TASKS_READ = "tasks.read"
    TASKS_UPDATE = "tasks.update"
    # Full credit decision with rule trace (module `decision`).
    DECISIONS_READ = "decisions.read"
    # Back office screens: queue, metrics (module `bff`); the check of a company by INN
    # before an application (module `clients`).
    BACKOFFICE_READ = "backoffice.read"
    # Feed and notifications (module `notifications`).
    FEED_READ = "feed.read"
