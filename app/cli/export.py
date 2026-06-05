import os
import sys
import json
import re
import gzip
import subprocess
import shutil
from datetime import datetime, timezone
from typing import Optional

from releascenify import parse_filename
from app.core.config import settings
from app.db.database import get_db_ctx
from app.db.models import DownloadLink
from sqlalchemy import select
from sqlalchemy.orm import selectinload

def clean_filename(filename):
    if not filename:
        return ""
    
    # Remove trailing size suffixes (e.g., " – 2.0 GB", " - 1.5 Go", " - 800 MB")
    filename = re.sub(r'\s*[–-—]\s*\d+(?:\.\d+)?\s*(?:GB|MB|KB|Go|Mo|Ko|G|M|K)\b.*$', '', filename, flags=re.IGNORECASE)
    
    sites_pattern = r'(wawacity|zone-telechargement|loadix)'
    
    # Prefix tags
    filename = re.sub(r'^' + sites_pattern + r'\.[a-z0-9-]+\s*[-_]\s*', '', filename, flags=re.IGNORECASE)
    filename = re.sub(r'^www\.' + sites_pattern + r'\.[a-z0-9-]+\s*[-_]\s*', '', filename, flags=re.IGNORECASE)
    filename = re.sub(r'^\[\s*(www\.)?' + sites_pattern + r'\.[a-z0-9-]+\s*\]\s*', '', filename, flags=re.IGNORECASE)
    
    # Brackets anywhere
    filename = re.sub(r'\[\s*(www\.)?' + sites_pattern + r'\.[a-z0-9-]+\s*\]', '', filename, flags=re.IGNORECASE)
    
    # Suffix tags (hyphen or underscore followed by site name and tld)
    filename = re.sub(r'[-_]\s*(www\.)?' + sites_pattern + r'\.[a-z]{2,4}\b', '', filename, flags=re.IGNORECASE)
    
    # Suffix tags with dot (e.g. .Loadix.fun before extension or end of string)
    filename = re.sub(r'\.(www\.)?' + sites_pattern + r'\.[a-z]{2,4}\b(?=\.|$)', '', filename, flags=re.IGNORECASE)
    
    # In-between dots
    filename = re.sub(r'\.(www\.)?' + sites_pattern + r'\.[a-z]{2,4}\b\.', '.', filename, flags=re.IGNORECASE)
    
    # Standard site names without TLD
    filename = re.sub(r'[-_]\s*(wawacity|zone-telechargement|loadix)\b', '', filename, flags=re.IGNORECASE)

    # General cleanup
    filename = re.sub(r'\.+', '.', filename)
    filename = re.sub(r'_+', '_', filename)
    filename = re.sub(r'\.-', '-', filename)
    filename = re.sub(r'-\.', '-', filename)
    
    filename = filename.strip('. _-')
    
    # Nettoyage final de sécurité
    filename = re.sub(r'[-_.]?(wawacity|zone-telechargement|loadix)[-_.]?', '.', filename, flags=re.IGNORECASE)
    filename = re.sub(r'\.+', '.', filename)
    filename = filename.strip('. _-')
    
    return filename

def run_git_cmd(args, cwd):
    res = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        raise Exception(f"Git command {' '.join(args)} failed: {res.stderr.strip()}")
    return res.stdout.strip()

def check_needs_push(clone_dir: str, branch: str) -> bool:
    try:
        run_git_cmd(["git", "rev-parse", "--verify", f"origin/{branch}"], cwd=clone_dir)
    except Exception:
        # Remote branch doesn't exist, we must push to create it
        return True
    try:
        log_out = run_git_cmd(["git", "log", f"origin/{branch}..{branch}", "--oneline"], cwd=clone_dir)
        return bool(log_out.strip())
    except Exception:
        return True

def get_authenticated_url(repo_url, username, token):
    if not repo_url:
        return ""
    if repo_url.startswith("https://") and username and token:
        # Strip the https:// and rebuild with authentication tokens
        return f"https://{username}:{token}@{repo_url[8:]}"
    return repo_url

class ExportCommands:
    @staticmethod
    async def run_export(export_type: str = "all", output_dir: Optional[str] = None, input_file: Optional[str] = None):
        print(f"--- Starting Export (Type: {export_type}) ---")
        
        # Default output directory
        if not output_dir:
            output_dir = settings.DATA_EXPORT_DIR
                
        print(f"Local output directory: {output_dir}")
        os.makedirs(output_dir, exist_ok=True)
        
        parsed_list = []
        seen_filenames = set()
        
        # 1. Fetch releases from DDLtower database
        db_links = []
        try:
            async with get_db_ctx() as session:
                stmt = select(DownloadLink).options(selectinload(DownloadLink.metadata_rel))
                res = await session.execute(stmt)
                db_links = res.scalars().all()
            print(f"Loaded {len(db_links)} link(s) from DDLtower database.")
        except Exception as e:
            print(f"Warning: Could not read from database: {e}")
            
        for link in db_links:
            filename = link.filename
            if not filename:
                continue
            
            cleaned_filename = clean_filename(filename)
            if cleaned_filename in seen_filenames:
                continue
                
            try:
                parsed = parse_filename(cleaned_filename)
            except ValueError:
                continue
                
            parsed['filename'] = cleaned_filename
            parsed['imdb_id'] = link.imdb_id
            parsed['link_source'] = link.source_name
            
            # Add official TMDB/IMDb title and year if available
            if link.metadata_rel:
                official_title = link.metadata_rel.title_fr or link.metadata_rel.official_title
                if official_title:
                    parsed['official_title'] = official_title
                if link.metadata_rel.year:
                    parsed['official_year'] = link.metadata_rel.year
            
            if link.last_checked:
                lc = link.last_checked
                if lc.tzinfo is None:
                    lc = lc.replace(tzinfo=timezone.utc)
                local_lc = lc.astimezone(datetime.now().astimezone().tzinfo)
                parsed['date_added'] = local_lc.strftime("%d/%m/%Y %H:%M:%S")
            else:
                parsed['date_added'] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                
            if link.size:
                parsed['size'] = link.size
            elif link.size_bytes:
                b = float(link.size_bytes)
                for unit in ['Bytes', 'KB', 'MB', 'GB', 'TB']:
                    if b < 1024.0:
                        parsed['size'] = f"{b:.2f} {unit}" if unit in ['GB', 'TB'] else f"{b:.0f} {unit}"
                        break
                    b /= 1024.0
            else:
                parsed['size'] = "N/A"
                
            parsed_list.append(parsed)
            seen_filenames.add(cleaned_filename)
            
        # 2. Optionally load and parse from external input file/JSON (parser_cli.py compatibility)
        if input_file:
            if not os.path.exists(input_file):
                print(f"Error: Input file '{input_file}' does not exist.")
                sys.exit(1)
            print(f"Reading extra releases from file: {input_file}")
            
            is_json_extract = False
            json_data = []
            releases = []
            
            if input_file.endswith('.json'):
                is_json_extract = True
                with open(input_file, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)
            else:
                with open(input_file, 'r', encoding='utf-8') as f:
                    releases = [line.strip() for line in f if line.strip()]
                    
            if is_json_extract:
                for record in json_data:
                    # record: [filename, last_checked, size, size_bytes, imdb_id, source_name]
                    filename = record[0]
                    if not filename:
                        continue
                    cleaned_filename = clean_filename(filename)
                    if cleaned_filename in seen_filenames:
                        continue
                        
                    last_checked = record[1]
                    size_val = record[2]
                    size_bytes = record[3]
                    imdb_id = record[4] if len(record) > 4 else None
                    link_source = record[5] if len(record) > 5 else None
                    
                    if not imdb_id:
                        m_imdb = re.search(r'imdbid[-_](tt\d+)', filename, re.I)
                        m_tmdb = re.search(r'tmdbid[-_](\d+)', filename, re.I)
                        if m_imdb:
                            imdb_id = m_imdb.group(1)
                        elif m_tmdb:
                            imdb_id = m_tmdb.group(1)
                            
                    try:
                        parsed = parse_filename(cleaned_filename)
                    except ValueError:
                        continue
                        
                    parsed['filename'] = cleaned_filename
                    parsed['imdb_id'] = imdb_id
                    parsed['link_source'] = link_source
                    
                    if last_checked:
                        parsed['date_added'] = last_checked
                    else:
                        parsed['date_added'] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        
                    if size_val:
                        parsed['size'] = size_val
                    elif size_bytes:
                        b = float(size_bytes)
                        for unit in ['Bytes', 'KB', 'MB', 'GB', 'TB']:
                            if b < 1024.0:
                                parsed['size'] = f"{b:.2f} {unit}" if unit in ['GB', 'TB'] else f"{b:.0f} {unit}"
                                break
                            b /= 1024.0
                    else:
                        parsed['size'] = "N/A"
                        
                    parsed_list.append(parsed)
                    seen_filenames.add(cleaned_filename)
            else:
                for r in releases:
                    cleaned_r = clean_filename(r)
                    if cleaned_r in seen_filenames:
                        continue
                        
                    try:
                        parsed = parse_filename(cleaned_r)
                    except ValueError:
                        continue
                        
                    parsed['filename'] = cleaned_r
                    
                    imdb_id = None
                    m_imdb = re.search(r'imdbid[-_](tt\d+)', r, re.I)
                    m_tmdb = re.search(r'tmdbid[-_](\d+)', r, re.I)
                    if m_imdb:
                        imdb_id = m_imdb.group(1)
                    elif m_tmdb:
                        imdb_id = m_tmdb.group(1)
                    parsed['imdb_id'] = imdb_id
                    
                    link_source = None
                    m_src = re.search(r'(?i)(wawacity|zone-telechargement)', r)
                    if m_src:
                        link_source = 'Wawacity' if m_src.group(1).lower() == 'wawacity' else 'Zone-Telechargement'
                    parsed['link_source'] = link_source
                    
                    parsed['date_added'] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    parsed['size'] = "N/A"
                    
                    parsed_list.append(parsed)
                    seen_filenames.add(cleaned_r)
                    
        # 3. Load existing releases from local output file if it exists to merge (incremental mode)
        existing_releases = []
        db_path = os.path.join(output_dir, "data.db.gz")
        if os.path.exists(db_path):
            try:
                with open(db_path, 'rb') as f:
                    compressed_data = f.read()
                json_str = gzip.decompress(compressed_data).decode('utf-8')
                loaded_data = json.loads(json_str)
                if isinstance(loaded_data, dict) and "keys" in loaded_data and "rows" in loaded_data:
                    keys_loaded = loaded_data["keys"]
                    for row in loaded_data["rows"]:
                        item = {}
                        for idx, val in enumerate(row):
                            if val is not None:
                                item[keys_loaded[idx]] = val
                        existing_releases.append(item)
                else:
                    existing_releases = loaded_data
                print(f"Loaded {len(existing_releases)} existing release(s) from {os.path.basename(db_path)}.")
            except Exception as e:
                print(f"Warning: Failed to load existing database: {e}")
                
        # Merge parsed_list into existing_releases, avoiding duplicates
        valid_existing_releases = []
        for item in existing_releases:
            fname = item.get('filename')
            if not fname:
                continue
            try:
                # Re-validate against the current parser rules to prune old junk
                parse_filename(fname)
                valid_existing_releases.append(item)
            except ValueError:
                print(f"[EXPORT] Excluding invalid/obfuscated existing release from merge: {fname}")
                continue

        existing_filenames = {item['filename'] for item in valid_existing_releases}
        merged_list = list(valid_existing_releases)
        
        for item in parsed_list:
            if item['filename'] not in existing_filenames:
                merged_list.append(item)
                existing_filenames.add(item['filename'])
                
        # Sort merged releases by date_added descending (newest first)
        def parse_date_added_merged(item):
            da = item.get("date_added")
            if not da:
                return datetime.min
            try:
                return datetime.strptime(da, "%d/%m/%Y %H:%M:%S")
            except Exception:
                return datetime.min
                
        merged_list.sort(key=parse_date_added_merged, reverse=True)
        
        # 4. Generate & Save output files
        generated_files = []
        
        if export_type in ("all", "data"):
            data_db_path = os.path.join(output_dir, "data.db.gz")
            keys = ['category', 'title', 'imdb_id', 'year', 'size', 'group', 'date_added', 'quality', 'resolution', 'codec', 'audio', 'season', 'episode', 'episode_name', 'channels', 'network', 'extra', 'filename', 'link_source', 'languages', 'v_quality', 'official_title', 'official_year']
            rows = []
            for item in merged_list:
                row = [item.get(k) for k in keys]
                rows.append(row)
            explorer_db = {
                "keys": keys,
                "rows": rows
            }
            merged_json = json.dumps(explorer_db, separators=(',', ':'), ensure_ascii=False)
            compressed_bytes = gzip.compress(merged_json.encode('utf-8'))
            with open(data_db_path, 'wb') as f:
                f.write(compressed_bytes)
            print(f"SUCCESS: Saved explorer database to: {data_db_path}")
            generated_files.append(("data.db.gz", compressed_bytes))
            
        if export_type in ("all", "stats"):
            stats_db_path = os.path.join(output_dir, "stats.db.gz")
            stats_keys = ['category', 'title', 'imdb_id', 'year', 'size', 'group', 'date_added', 'quality', 'resolution', 'codec', 'audio', 'v_quality', 'official_title', 'official_year']
            stats_rows = []
            for item in merged_list:
                row = [item.get(k) for k in stats_keys]
                stats_rows.append(row)
            stats_db = {
                "keys": stats_keys,
                "rows": stats_rows
            }
            minimized_json = json.dumps(stats_db, separators=(',', ':'), ensure_ascii=False)
            compressed_stats_bytes = gzip.compress(minimized_json.encode('utf-8'))
            with open(stats_db_path, 'wb') as f:
                f.write(compressed_stats_bytes)
            print(f"SUCCESS: Saved stats database to: {stats_db_path}")
            generated_files.append(("stats.db.gz", compressed_stats_bytes))
            
        # 5. Remote git commit & push if enabled
        if settings.GIT_ENABLED:
            print("--- [GIT] Git Remote Sync Operations ---")
            if not settings.GIT_REPO_URL:
                print("ERROR: git.repo_url is not configured.")
                return
                
            clone_dir = settings.GIT_CLONE_DIR
            os.makedirs(clone_dir, exist_ok=True)
            
            # Setup repo
            auth_url = get_authenticated_url(settings.GIT_REPO_URL, settings.GIT_USERNAME, settings.GIT_TOKEN)
            if not os.path.exists(os.path.join(clone_dir, ".git")):
                print(f"[GIT] Cloning default branch from remote...")
                if os.path.exists(clone_dir) and os.listdir(clone_dir):
                    print(f"[GIT] Cleaning clone directory {clone_dir}...")
                    shutil.rmtree(clone_dir)
                    os.makedirs(clone_dir, exist_ok=True)
                run_git_cmd(["git", "clone", auth_url, "."], cwd=clone_dir)
            else:
                print(f"[GIT] Updating remote URL and fetching...")
                run_git_cmd(["git", "remote", "set-url", "origin", auth_url], cwd=clone_dir)
                run_git_cmd(["git", "fetch", "--prune", "origin"], cwd=clone_dir)
                
            # Config credentials in repo
            if settings.GIT_USERNAME:
                run_git_cmd(["git", "config", "user.name", settings.GIT_USERNAME], cwd=clone_dir)
            if settings.GIT_EMAIL:
                run_git_cmd(["git", "config", "user.email", settings.GIT_EMAIL], cwd=clone_dir)
                
            # Checkout or create branch
            try:
                # Check if remote branch exists
                run_git_cmd(["git", "rev-parse", "--verify", f"origin/{settings.GIT_BRANCH}"], cwd=clone_dir)
                # Orphan commit strategy: ignore existing branch state
                pass
            except Exception:
                pass

            # Create an orphan commit (no history) on the data branch.
            # This ensures the branch always has exactly one commit → constant size.
            # --orphan fails if we're currently ON that branch (can't delete the checked-out branch).
            # Fix: detach HEAD first, then delete the local branch, then create the orphan.
            print(f"[GIT] Creating orphan commit on branch '{settings.GIT_BRANCH}'...")
            try:
                run_git_cmd(["git", "checkout", "--detach"], cwd=clone_dir)
            except Exception:
                pass  # already detached or no commits yet, that's fine
            try:
                run_git_cmd(["git", "branch", "-D", settings.GIT_BRANCH], cwd=clone_dir)
                print(f"[GIT] Deleted existing local branch '{settings.GIT_BRANCH}'.")
            except Exception:
                pass  # branch didn't exist locally, that's fine
            run_git_cmd(["git", "checkout", "--orphan", settings.GIT_BRANCH], cwd=clone_dir)

            # Stage only the files we want to export (clean working tree first)
            run_git_cmd(["git", "rm", "-rf", "--cached", "."], cwd=clone_dir)

            # Find the best target directory in repo to place the files
            git_target_dir = clone_dir
            if os.path.isdir(os.path.join(clone_dir, "web", "data")):
                git_target_dir = os.path.join(clone_dir, "web", "data")
            elif os.path.isdir(os.path.join(clone_dir, "data")):
                git_target_dir = os.path.join(clone_dir, "data")

            print(f"[GIT] Copying files to: {git_target_dir}")
            os.makedirs(git_target_dir, exist_ok=True)

            files_added = []
            for fname, fbytes in generated_files:
                # Filter files based on git export type if specified
                if settings.GIT_EXPORT_TYPE == "stats" and fname != "stats.db.gz":
                    print(f"[GIT] Skipping {fname} from Git sync (GIT_EXPORT_TYPE is stats)")
                    continue
                if settings.GIT_EXPORT_TYPE == "data" and fname != "data.db.gz":
                    print(f"[GIT] Skipping {fname} from Git sync (GIT_EXPORT_TYPE is data)")
                    continue

                git_file_path = os.path.join(git_target_dir, fname)
                with open(git_file_path, "wb") as f:
                    f.write(fbytes)
                rel_git_path = os.path.relpath(git_file_path, clone_dir)
                run_git_cmd(["git", "add", rel_git_path], cwd=clone_dir)
                files_added.append(fname)

            if files_added:
                print("[GIT] Committing orphan snapshot...")
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                run_git_cmd(["git", "commit", "-m", f"update data: {timestamp}"], cwd=clone_dir)
                print("[GIT] Force-pushing orphan commit to remote (single-commit branch)...")
                run_git_cmd(["git", "push", "origin", settings.GIT_BRANCH, "--force"], cwd=clone_dir)
                print("[GIT] Push completed successfully!")

                # --- Update CHANGELOG.md on main branch to trigger Github Actions ---
                print("[GIT] Updating CHANGELOG.md on main branch to trigger workflow...")
                try:
                    run_git_cmd(["git", "fetch", "origin", "main"], cwd=clone_dir)
                    run_git_cmd(["git", "checkout", "-f", "main"], cwd=clone_dir)
                    run_git_cmd(["git", "pull", "origin", "main"], cwd=clone_dir)
                    
                    changelog_path = os.path.join(clone_dir, "CHANGELOG.md")
                    new_entry = f"## Mise à jour automatique\n- **Date :** {timestamp}\n- **Entrées totales :** {len(merged_list)}\n\n"
                    
                    if os.path.exists(changelog_path):
                        with open(changelog_path, "r", encoding="utf-8") as f:
                            existing_content = f.read()
                    else:
                        existing_content = "# Historique des mises à jour\n\n"
                        
                    with open(changelog_path, "w", encoding="utf-8") as f:
                        f.write(new_entry + existing_content)
                        
                    run_git_cmd(["git", "add", "CHANGELOG.md"], cwd=clone_dir)
                    run_git_cmd(["git", "commit", "-m", f"docs: update changelog {timestamp}"], cwd=clone_dir)
                    run_git_cmd(["git", "push", "origin", "main"], cwd=clone_dir)
                    print("[GIT] CHANGELOG.md updated and pushed to main branch successfully!")
                except Exception as e:
                    print(f"[GIT] Warning: Failed to update CHANGELOG.md on main branch: {e}")

            else:
                print("[GIT] No files to export, skipping commit.")
