# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "click",
#     "httpx",
# ]
# ///

import click
import sqlite3
import httpx
import json
from datetime import date

SCHEMA = """
CREATE TABLE IF NOT EXISTS federal_register_documents(
  document_number text PRIMARY KEY,
  title text,
  abstract text,
  document_type text,
  agencies json,
  excerpts text,
  html_url text,
  pdf_url text,
  public_inspection_pdf_url text
);

CREATE TABLE IF NOT EXISTS federal_register_agencies(
  id integer PRIMARY KEY,
  parent_id integer REFERENCES federal_register_agencies(id),
  slug text,
  name text,
  short_name text,
  description text,
  url text,
  child_ids json
);
"""


@click.group()
def cli():
    """Federal Register data processing tools."""
    pass


def backfill_agencies(db):
    """Backfill Federal Register agencies into the database."""
    response = httpx.get("https://www.federalregister.gov/api/v1/agencies").json()

    with db:
        for agency in response:
            db.execute(
                "INSERT OR IGNORE INTO federal_register_agencies (id, parent_id, slug, name, short_name, description, url, child_ids) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    agency["id"],
                    agency.get("parent_id"),
                    agency["slug"],
                    agency["name"],
                    agency.get("short_name", ""),
                    agency.get("description", ""),
                    agency.get("url", ""),
                    json.dumps(agency.get("child_ids", [])),
                ),
            )


@cli.command()
@click.argument("output")
@click.option(
    "--until",
    required=False,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="End date in YYYY-MM-DD format",
    default=date.today(),
)
def sync(output, until):
    """Backfill Federal Register data into a database."""
    click.echo(f"Backfilling data to {output} until {until.strftime('%Y-%m-%d')}")
    db = sqlite3.connect(output)
    with db:
        db.executescript(SCHEMA)

    agency_id = db.execute(
        "select id from federal_register_agencies limit 1"
    ).fetchone()

    if not agency_id:
        backfill_agencies(db)

    response = httpx.get(
        f"https://www.federalregister.gov/api/v1/documents.json?per_page=1000&conditions[publication_date][lte]={until}"
    ).json()

    changes = 0
    with db:
        for result in response["results"]:
            document_number = result["document_number"]
            title = result["title"]
            abstract = result.get("abstract", "")
            document_type = result["type"]
            agencies = json.dumps([agency.get("id") for agency in result["agencies"]])
            excerpts = result.get("excerpts", "")
            html_url = result["html_url"]
            pdf_url = result.get("pdf_url", "")
            public_inspection_pdf_url = result.get("public_inspection_pdf_url", "")

            db.execute(
                "INSERT OR IGNORE INTO federal_register_documents (document_number, title, abstract, document_type, agencies, excerpts, html_url, pdf_url, public_inspection_pdf_url) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    document_number,
                    title,
                    abstract,
                    document_type,
                    agencies,
                    excerpts,
                    html_url,
                    pdf_url,
                    public_inspection_pdf_url,
                ),
            )
            changes += db.execute("select changes()").fetchone()[0]

    click.echo("Loaded {} documents into the database.".format(changes))


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
