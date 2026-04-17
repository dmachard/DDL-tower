import argparse
import asyncio
import sys
from app.cli.db import DBCommands
from app.cli.tags import TagCommands
from app.cli.links import LinkCommands
from app.cli.scan import ScanCommands

async def run_cli():
    from app.db.database import init_db
    await init_db()
    
    parser = argparse.ArgumentParser(description="DDLtower CLI Maintenance Tool")
    subparsers = parser.add_subparsers(dest="command", help="Command namespace")

    # [Existing parser definitions...]
    db_parser = subparsers.add_parser("db", help="Database operations")
    db_sub = db_parser.add_subparsers(dest="subcommand", help="DB subcommand")
    
    backup_p = db_sub.add_parser("backup", help="Export DB to JSON")
    backup_p.add_argument("--output", default="data/backup.json", help="Path to backup file")
    
    restore_p = db_sub.add_parser("restore", help="Import DB from JSON")
    restore_p.add_argument("--input", default="data/backup.json", help="Path to backup file")
    
    reset_scans_p = db_sub.add_parser("reset-scans", help="Clear scraping history")
    reset_scans_p.add_argument("--pattern", help="Filter by URL pattern")
    
    reset_meta_p = db_sub.add_parser("reset-metadata", help="Clear metadata for re-enrichment")
    reset_meta_p.add_argument("--title", help="Search by title")
    reset_meta_p.add_argument("--id", help="Exact IMDb ID")
    
    cleanup_p = db_sub.add_parser("cleanup", help="Fix database data")
    audit_p = db_sub.add_parser("audit", help="Audit database metadata health")

    # db update-title
    update_title_p = db_sub.add_parser("update-title", help="Manually rename a link title")
    update_title_p.add_argument("--id", type=int, help="Specific Link ID")
    update_title_p.add_argument("--title", help="Old title to find")
    update_title_p.add_argument("--new-title", required=True, help="New title to apply")
    reset_all_p = db_sub.add_parser("reset-all", help="WIPE ALL metadata and start fresh")
    wipe_p = db_sub.add_parser("wipe", help="COMPLETELY WIPE DATABASE (Links, History, Metadata)")

    tag_parser = subparsers.add_parser("tag", help="Metadata tagging/matching")
    tag_parser.add_argument("--title", help="Specify a title to tag manually")
    tag_parser.add_argument("--rename-to", help="Rename found links to this title before tagging")
    tag_parser.add_argument("--year", type=int, help="Force a specific year")
    tag_parser.add_argument("--type", choices=["movie", "series"], help="Force media type")
    tag_parser.add_argument("--limit", type=int, default=500, help="Batch limit if no title specified")
    tag_parser.add_argument("--repair", action="store_true", help="Repair existing metadata (missing plot/posters)")
    tag_parser.add_argument("--id", help="Force a specific IMDb ID")

    links_parser = subparsers.add_parser("links", help="Link management")
    links_sub = links_parser.add_subparsers(dest="subcommand", help="Links subcommand")
    
    reverify_p = links_sub.add_parser("reverify", help="Re-check dead links")
    view_p = links_sub.add_parser("view", help="Show detailed item data")
    view_p.add_argument("query", help="Title or partial filename to view")
    
    scan_parser = subparsers.add_parser("scan", help="Manually trigger a full scan of all sources")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == "db":
            if args.subcommand == "backup":
                await DBCommands.backup(args.output)
            elif args.subcommand == "restore":
                await DBCommands.restore(args.input)
            elif args.subcommand == "reset-scans":
                await DBCommands.reset_scans(args.pattern)
            elif args.subcommand == "reset-metadata":
                await DBCommands.reset_metadata(args.title, args.id)
            elif args.subcommand == "cleanup":
                await DBCommands.cleanup()
            elif args.subcommand == "audit":
                await DBCommands.audit()
            elif args.subcommand == "update-title":
                await DBCommands.update_title(args.id, args.title, args.new_title)
            elif args.subcommand == "reset-all":
                await DBCommands.reset_all()
            elif args.subcommand == "wipe":
                await DBCommands.wipe()
            else:
                db_parser.print_help()

        elif args.command == "tag":
            await TagCommands.process(
                title=args.title,
                rename_to=args.rename_to,
                year=args.year, 
                media_type=args.type, 
                limit=args.limit,
                repair=args.repair,
                imdb_id=args.id
            )

        elif args.command == "links":
            if args.subcommand == "reverify":
                await LinkCommands.reverify()
            elif args.subcommand == "view":
                await LinkCommands.view(args.query)
            else:
                links_parser.print_help()
        
        elif args.command == "scan":
            await ScanCommands.trigger()

    except Exception as e:
        print(f"Error executing command: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def main():
    asyncio.run(run_cli())

if __name__ == "__main__":
    main()
