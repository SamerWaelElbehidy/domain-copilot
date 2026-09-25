from enum import Enum


class Role(str, Enum):
    TECHNICIAN = "technician"
    SUPERVISOR = "supervisor"
    ADMIN = "admin"


class Permission(str, Enum):
    ASK = "ask"
    START_RUN = "start_run"
    VIEW_OWN_RUNS = "view_own_runs"
    VIEW_ALL_RUNS = "view_all_runs"
    DECIDE_WORK_ORDER = "decide_work_order"
    REPLAY_RUN = "replay_run"
    INGEST_DOCUMENTS = "ingest_documents"
    VIEW_USAGE = "view_usage"


# Separation of duties is a business rule, so it lives in the domain and is
# enforced server-side (FR-8). The person who raises a work order cannot
# approve it, and an admin can inspect and replay everything but cannot
# approve dispatch: only a supervisor holds the pen.
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.TECHNICIAN: frozenset(
        {Permission.ASK, Permission.START_RUN, Permission.VIEW_OWN_RUNS}
    ),
    Role.SUPERVISOR: frozenset(
        {
            Permission.ASK,
            Permission.VIEW_OWN_RUNS,
            Permission.VIEW_ALL_RUNS,
            Permission.DECIDE_WORK_ORDER,
            Permission.REPLAY_RUN,
        }
    ),
    Role.ADMIN: frozenset(
        {
            Permission.ASK,
            Permission.VIEW_OWN_RUNS,
            Permission.VIEW_ALL_RUNS,
            Permission.REPLAY_RUN,
            Permission.INGEST_DOCUMENTS,
            Permission.VIEW_USAGE,
        }
    ),
}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]
