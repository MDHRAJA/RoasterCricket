"""Write an evidence-based collection report and portable, checksum-verified ZIP."""
import csv
import hashlib
import json
import zipfile
from pathlib import Path
from fetch_data import DATA, ROOT


def main():
    summary=json.loads((DATA/'coverage_summary.json').read_text(encoding='utf-8'))
    checks=json.loads((DATA/'validation_report.json').read_text(encoding='utf-8'))
    tests=json.loads((DATA/'independent_tests.json').read_text(encoding='utf-8'))
    if not all(c['passed'] for c in checks) or tests['failures']:
        raise SystemExit('Cannot package data with failed checks')
    catalog=json.loads((DATA/'dataset_catalog.json').read_text(encoding='utf-8'))
    players=list(csv.DictReader((DATA/'processed/players.csv').open(encoding='utf-8')))
    squads=list(csv.DictReader((DATA/'processed/squads_current.csv').open(encoding='utf-8')))
    selected={r['player_id'] for r in squads}
    roles={r['player_id'] for r in squads if r['official_role'] in ('bowler','allrounder')}
    unresolved_roles=[r for r in players if not r['primary_role']]
    bowlers=[r for r in players if r['player_id'] in roles]
    coverage=sum(bool(r['bowling_category']) for r in bowlers)
    rules_saved=(DATA/'raw/ipl/TATA_IPL_2026_Match_Playing_Conditions_current.pdf').exists()
    failures=[]
    for name in ['source_manifest.json','enrichment_manifest.json','extra_sources_manifest.json','documents_manifest.json']:
        for r in json.loads((DATA/name).read_text(encoding='utf-8')):
            if r['status']=='failed': failures.append(r)
    lines=[
        '# IPL data collection report', '',
        'Collected 2 October 2026. Core data is saved locally and validated. This report distinguishes collected facts, derived descriptions and outstanding inputs.', '',
        '## Saved coverage', '',
        f'- {summary["matches"]:,} Cricsheet IPL match records across {len(summary["seasons"])} seasons (2008-2026).',
        f'- {summary["deliveries"]:,} recorded deliveries, including separately flagged Super Overs.',
        f'- Date range: {summary["first_match"]} to {summary["latest_match"]}.',
        f'- {summary["players"]:,} player identities: {summary["historical_players"]} with archive participation and {summary["players"]-summary["historical_players"]} additional snapshot players.',
        f'- Ten official 2026 roster snapshots, {summary["current_squad_rows"]} entries. These include replaced players and are not an eligibility/fitness list.',
        f'- {summary["venues"]} reviewed stadium identities from 60 original labels.',
        f'- {summary["datasets"]} processed CSV datasets plus an indexed SQLite mirror.',
        f'- Build checks: {summary["passed_checks"]}/{summary["total_checks"]}; independent tests: {tests["passed"]}/{tests["tests_run"]}.', '',
        '## Player metadata coverage', '',
        f'- Batting hand and primary role are sourced for all {len(selected)} snapshot members; no missing batting hands across the {len(players)}-player master.',
        f'- All {coverage}/{len(bowlers)} officially labelled roster bowlers/all-rounders have a reported bowling category.',
        f'- {summary["current_missing_bowling_style"]} current snapshot batters/keepers have no published bowling style in the selected sources; this does not mean they cannot bowl.',
        f'- {len(unresolved_roles)} historical player primary roles remain unpublished in the collected metadata. See metadata_review.csv; do not guess them from observed wickets/runs.',
        f'- {summary["current_only_local_ids"]} current players retain stable official IPL local IDs because a safe Cricsheet identity join was not established.',
        '- One explicit bowling-style conflict: Daksh Kamra (official KKR Off Spin vs Cricbuzz legbreak). Retain spin/right-arm at coarse level; review before fine-grained modelling.',
        '- Amit Kumar (SRH) supplemental attributes are provisional secondary-source facts, not an official IPL profile; identically named players were not merged.',
        f'- Historical delivery bowling-category coverage: {100*summary["historical_delivery_bowling_category_coverage"]:.5f}%. Career categories are not ball-level tracking measurements.', '',
        '## Descriptive features ready for development', '',
        'Player season and match statistics; last-5/10 form timelines and run-trend slope; batter-bowler and bowling-style/hand matchups; powerplay/middle/death phase splits; player/venue profiles; toss/result/target fields; wicket/fielding and replacement events. Raw stage metadata supports stage filters where supplied.', '',
        'These are descriptive inputs. No Bayesian posterior, simulated win probability or optimized XI has been calculated. Whole-season aggregates and after-match form must not leak into historical pre-match predictions.', '',
        '## Outstanding or unavailable layers', '',
        '- Match-day registration/fitness/injuries/availability: manual template initialized to unknown; no comprehensive live feed collected.',
        '- Measured historical pitch state, dew and weather: not in ball-by-ball archive; empty scenario-input template provided.',
        '- Upcoming fixtures: no invented future-season schedule. The identified 2026 schedule document was a partial initial schedule and could not be downloaded.',
        '- Full historical registered/bench squads: match-observed membership is collected instead; do not equate it with all contracted players.',
        ('- Official 2026 playing-conditions PDF: saved unmodified (119 pages) through the download link embedded in the official IPL page. Cover says effective March 2026; introduction says March 2024. See rules_document_verification.json. Annual constraints and any supplemental Impact Player regulations still require review before implementation.' if rules_saved else '- Annual roster/Impact eligibility rules: official reference page saved, but identified PDF downloads were refused. Verify the applicable season before enabling constraints.'),
        '- Fielding events outside dismissals, tracking metrics and per-ball style changes: absent from selected sources.', '',
        '### Original document-server download attempts', '',
    ]
    for r in failures:
        resolved=(DATA/r['file']).exists()
        status='File subsequently saved through the public official IPL website download link; original refused attempt retained for audit.' if resolved else 'Reference logged; this binary PDF is **not saved**.'
        lines.append(f'- [{Path(r["file"]).name}]({r["source_url"]}): {r["error"]}. {status}')
    if rules_saved:
        lines += ['', 'The collected official rules PDF is [saved here](raw/ipl/TATA_IPL_2026_Match_Playing_Conditions_current.pdf). Its successful retrieval URL, byte count and SHA-256 are recorded in rules_download_manifest.json.']
    lines += ['', '## Dataset inventory', '', '| Dataset | Rows | Local file |', '| --- | ---: | --- |']
    for r in catalog:
        path=DATA/r['path']
        actual=hashlib.sha256(path.read_bytes()).hexdigest()
        if actual!=r['sha256']: raise ValueError(f'Catalog checksum mismatch: {path}')
        lines.append(f'| {r["dataset"]} | {r["rows"]:,} | [{path.name}]({r["path"]}) |')
    lines += ['', '## Sources and use', '',
        'Match data: [Cricsheet](https://cricsheet.org/downloads/). Stable identities: [Cricsheet Register](https://cricsheet.org/register/). Base metadata: [cricketdata](https://github.com/robjhyndman/cricketdata), with 2025 snapshot documentation. Updated attributes: saved public ESPN JSON profiles plus individually cited ICC/franchise/provider facts. Rosters: [official IPL teams](https://www.iplt20.com/teams). See the raw manifests and per-field sources for exact URLs and retrieval checksums.', '',
        'Source-specific attribution and terms apply. This local pack is not universally open-licensed; review redistribution/commercial rights before public deployment. Source PDFs that refused access have not been bypassed.', '',
        'Read [DATA_DICTIONARY.md](DATA_DICTIONARY.md) for denominator/phase/identity definitions, and [README.md](README.md) for rebuild steps and the complete readiness matrix.', '',
        'Next development boundary: an API over the validated database, then time-safe Bayesian modelling and calibration; frontend work can proceed with these real records without fabricated forecasts.', '']
    (DATA/'collection_report.md').write_text('\n'.join(lines),encoding='utf-8')
    inventory=[]
    for path in sorted(DATA.rglob('*')):
        if path.is_file() and path.name!='file_manifest.json':
            inventory.append({'path':path.relative_to(DATA).as_posix(),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    (DATA/'file_manifest.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
    bundle=ROOT/'outputs/ipl-datasets-2026-10-02.zip'
    with zipfile.ZipFile(bundle,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(DATA.rglob('*')):
            if path.is_file(): z.write(path,'ipl-data/'+path.relative_to(DATA).as_posix())
        for folder in ['scripts','config']:
            for path in sorted((ROOT/folder).rglob('*')):
                if path.is_file() and '__pycache__' not in path.parts:
                    z.write(path,'pipeline/'+path.relative_to(ROOT).as_posix())
        z.write(ROOT/'requirements-data.txt','pipeline/requirements-data.txt')
    with zipfile.ZipFile(bundle) as z:
        error=z.testzip()
        if error: raise ValueError(f'ZIP integrity failed at {error}')
        members=len(z.namelist())
    result={'bundle':str(bundle),'bytes':bundle.stat().st_size,'sha256':hashlib.sha256(bundle.read_bytes()).hexdigest(),'files':members,'zip_integrity':'passed'}
    (ROOT/'outputs/bundle_manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
