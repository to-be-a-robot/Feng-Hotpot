"""Manage who can sign in (for AUTH_MODE=supabase).

    python -m feng_workers.users add manager@feng.example --role manager --locations sunnyvale
    python -m feng_workers.users add staff@feng.example --role staff --locations sunnyvale --password '...'
    python -m feng_workers.users list
    python -m feng_workers.users remove staff@feng.example

`add` creates the Supabase Auth user (email confirmed, so magic links work at
once; --password also allows password sign-in, for backup demo accounts) and
upserts the profiles row with role and locations. Re-running `add` updates the
role/locations. `remove` deletes the profile, which blocks API access; the
auth user stays (delete it in the Supabase dashboard if needed).

Needs SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and DATABASE_URL. The service-role
key is admin access: keep it on your machine and the server, never in the frontend.
"""

from __future__ import annotations

import argparse

import httpx

from .config import env

ROLES = ("manager", "staff", "admin")


def _admin_headers() -> dict:
    key = env("SUPABASE_SERVICE_ROLE_KEY", required=True)
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def find_auth_user(email: str) -> dict | None:
    url = env("SUPABASE_URL", required=True)
    page = 1
    while True:
        r = httpx.get(f"{url}/auth/v1/admin/users", params={"page": page, "per_page": 200},
                      headers=_admin_headers(), timeout=20)
        r.raise_for_status()
        users = r.json().get("users", [])
        for u in users:
            if (u.get("email") or "").lower() == email.lower():
                return u
        if len(users) < 200:
            return None
        page += 1


def ensure_auth_user(email: str, password: str | None = None) -> str:
    """Create the Supabase Auth user if needed; return its id."""
    url = env("SUPABASE_URL", required=True)
    body = {"email": email, "email_confirm": True}
    if password:
        body["password"] = password
    r = httpx.post(f"{url}/auth/v1/admin/users", json=body, headers=_admin_headers(), timeout=20)
    if r.status_code in (200, 201):
        return r.json()["id"]
    existing = find_auth_user(email)
    if existing is None:
        raise SystemExit(f"Supabase refused to create {email}: HTTP {r.status_code} {r.text[:200]}")
    if password:
        httpx.put(f"{url}/auth/v1/admin/users/{existing['id']}", json={"password": password},
                  headers=_admin_headers(), timeout=20).raise_for_status()
    return existing["id"]


def upsert_profile(conn, user_id: str, role: str, locations: list[str], name: str | None):
    if role not in ROLES:
        raise SystemExit(f"role must be one of {ROLES}")
    known = {r[0] for r in conn.execute("select slug from locations")}
    unknown = [l for l in locations if l not in known]
    if unknown:
        raise SystemExit(f"unknown locations {unknown}; known: {sorted(known)}")
    conn.execute(
        """
        insert into profiles (user_id, role, locations, display_name) values (%s, %s, %s, %s)
        on conflict (user_id) do update set role = excluded.role, locations = excluded.locations,
                                            display_name = coalesce(excluded.display_name, profiles.display_name)
        """, (user_id, role, locations, name))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add")
    add.add_argument("email")
    add.add_argument("--role", choices=ROLES, required=True)
    add.add_argument("--locations", default="sunnyvale", help="comma-separated location slugs")
    add.add_argument("--password", help="also allow password sign-in (backup demo accounts)")
    add.add_argument("--name", help="display name shown as the approver")
    sub.add_parser("list")
    rm = sub.add_parser("remove")
    rm.add_argument("email")
    args = ap.parse_args(argv)

    from .db import connect
    with connect() as conn:
        if args.cmd == "add":
            uid = ensure_auth_user(args.email, args.password)
            locs = [l.strip() for l in args.locations.split(",") if l.strip()]
            upsert_profile(conn, uid, args.role, locs, args.name or args.email.split("@")[0])
            conn.commit()
            print(f"{args.email}: {args.role} at {', '.join(locs)} (user {uid})")
        elif args.cmd == "list":
            rows = conn.execute("select user_id, role, locations, display_name from profiles order by role").fetchall()
            for uid, role, locs, name in rows:
                print(f"{role:8} {','.join(locs):20} {name or ''}  ({uid})")
            if not rows:
                print("No profiles yet.")
        else:
            u = find_auth_user(args.email)
            if not u:
                raise SystemExit(f"No Supabase user {args.email}")
            conn.execute("delete from profiles where user_id = %s", (u["id"],))
            conn.commit()
            print(f"Removed {args.email}'s access (auth user kept).")


if __name__ == "__main__":
    main()
