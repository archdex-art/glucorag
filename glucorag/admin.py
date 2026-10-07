"""Server-side account administration (run on the host, against the service database).

    glucorag-admin create-clinician nurse@ward.example     # prompts for a password
    glucorag-admin list-users
    glucorag-admin reset-password someone@example.com

Self-registration on the website only ever creates personal accounts; clinician
accounts, which can see every patient, are created here by whoever runs the server.
"""

import argparse
import getpass
import sys
from pathlib import Path

from glucorag.api.settings import ApiSettings
from glucorag.core.accounts import (
    WeakPasswordError,
    check_password_policy,
    hash_password,
    new_patient_id,
)
from glucorag.core.storage import Storage


def _password(prompt: str) -> str:
    first = getpass.getpass(prompt)
    if getpass.getpass("Repeat: ") != first:
        raise SystemExit("Passwords do not match.")
    try:
        check_password_policy(first)
    except WeakPasswordError as e:
        raise SystemExit(str(e)) from e
    return first


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--db-path", type=Path, help="defaults to GLUCORAG_DB_PATH")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-clinician")
    c.add_argument("email")
    sub.add_parser("list-users")
    r = sub.add_parser("reset-password")
    r.add_argument("email")
    args = p.parse_args(argv)

    storage = Storage(args.db_path or ApiSettings().db_path)
    try:
        if args.cmd == "create-clinician":
            email = args.email.strip().lower()
            pw = _password(f"Password for {email}: ")
            try:
                storage.create_user(email, hash_password(pw), "clinician", new_patient_id())
            except ValueError as e:
                raise SystemExit(f"{email} is already registered.") from e
            print(f"Created clinician account {email}.")
        elif args.cmd == "list-users":
            for u in storage.users():
                print(f"{u.id}\t{u.role}\t{u.email}\t{u.created_at:%Y-%m-%d}")
        else:
            found = storage.user_credentials(args.email.strip().lower())
            if found is None:
                raise SystemExit("No such account.")
            user = found[0]
            storage.set_password_hash(user.id, hash_password(_password("New password: ")))
            storage.delete_user_sessions(user.id)
            print(f"Password reset for {user.email}; all their sessions were signed out.")
    finally:
        storage.close()


if __name__ == "__main__":
    main(sys.argv[1:])
