import argparse
import asyncio
import hashlib
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg

ROLES = ("owner", "coach", "ga", "viewer")


async def provision(args: argparse.Namespace) -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    conn = await asyncpg.connect(database_url, command_timeout=15)
    try:
        async with conn.transaction():
            program_id = uuid.UUID(args.program_id) if args.program_id else uuid.uuid4()
            program = await conn.fetchrow("SELECT id,name FROM programs WHERE id=$1", program_id)
            if program is None:
                if not args.program_name:
                    raise SystemExit("--program-name is required when creating a new program")
                await conn.execute(
                    """
                    INSERT INTO programs (id,name,level,external_source,external_id)
                    VALUES ($1,$2,'college','fieldmind_customer',$3)
                    """,
                    program_id,
                    args.program_name,
                    str(program_id),
                )

            user_id = await conn.fetchval(
                """
                INSERT INTO users (email,display_name)
                VALUES ($1,$2)
                ON CONFLICT (email) DO UPDATE SET
                    display_name=COALESCE(EXCLUDED.display_name,users.display_name),
                    active=true
                RETURNING id
                """,
                args.email,
                args.display_name,
            )
            await conn.execute(
                """
                INSERT INTO program_memberships (program_id,user_id,role)
                VALUES ($1,$2,$3)
                ON CONFLICT (program_id,user_id) DO UPDATE SET role=EXCLUDED.role
                """,
                program_id,
                user_id,
                args.role,
            )
            if args.revoke_existing:
                await conn.execute(
                    "UPDATE auth_tokens SET revoked_at=now() WHERE user_id=$1 AND revoked_at IS NULL",
                    user_id,
                )

            raw_token = secrets.token_urlsafe(48)
            token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
            expires_at = datetime.now(timezone.utc) + timedelta(days=args.days)
            await conn.execute(
                """
                INSERT INTO auth_tokens (user_id,token_hash,expires_at)
                VALUES ($1,$2,$3)
                """,
                user_id,
                token_hash,
                expires_at,
            )
    finally:
        await conn.close()

    print(f"program_id={program_id}")
    print(f"user_id={user_id}")
    print(f"role={args.role}")
    print(f"expires_at={expires_at.isoformat()}")
    print("token_printed_once=true")
    print(f"FIELDMIND_TOKEN={raw_token}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Provision one FIELDMIND pilot user and bearer token.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--display-name")
    parser.add_argument("--role", choices=ROLES, required=True)
    parser.add_argument("--program-id", help="Existing program UUID. Omit to create a customer program.")
    parser.add_argument("--program-name", help="Required when --program-id is omitted.")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--revoke-existing", action="store_true")
    args = parser.parse_args()
    if args.days < 1 or args.days > 90:
        parser.error("--days must be between 1 and 90")
    if not args.program_id and not args.program_name:
        parser.error("--program-name is required when creating a new program")
    return args


if __name__ == "__main__":
    asyncio.run(provision(parse_args()))
