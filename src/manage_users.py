"""
Gestion des comptes en ligne de commande (aucun compte par défaut, aucun mot de passe en dur).

Exemples :
    python -m src.manage_users add alice
    python -m src.manage_users list
    python -m src.manage_users unlock alice
    python -m src.manage_users delete alice
"""

import argparse
import getpass
import sys

from src.auth import PasswordPolicyError, UserStore


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Gestion des comptes du dashboard")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("add", "delete", "unlock"):
        sub.add_parser(name).add_argument("username")
    sub.add_parser("list")
    args = parser.parse_args(argv)

    store = UserStore()
    if args.command == "add":
        password = getpass.getpass("Mot de passe : ")
        if password != getpass.getpass("Confirmation : "):
            print("Les mots de passe ne correspondent pas.", file=sys.stderr)
            return 1
        try:
            store.create_user(args.username, password)
        except (PasswordPolicyError, ValueError) as exc:
            print(f"Erreur : {exc}", file=sys.stderr)
            return 1
        print(f"Compte « {args.username} » créé.")
    elif args.command == "delete":
        print("Compte supprimé." if store.delete_user(args.username) else "Compte introuvable.")
    elif args.command == "unlock":
        store.unlock_user(args.username)
        print("Compte déverrouillé.")
    else:
        for user in store.list_users():
            print(user)
    return 0


if __name__ == "__main__":
    sys.exit(main())
