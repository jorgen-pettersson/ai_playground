import logging
import os
import json
from pathlib import Path
from urllib.parse import quote, unquote

from chunk_repository import (
    connect_db,
    default_db_url,
    get_slide_for_recording,
    list_course_recordings,
    list_slides_for_recording as list_slides_for_recording_rows,
)
from course_rag import DEFAULT_COURSE_ID
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.resources import FileResource, TextResource


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("mcp_server")

OUTPUT_DIR = (Path(__file__).resolve().parent / "output").resolve()

mcp = FastMCP("Forestry Course MCP")
mcp.settings.host = os.environ.get("MCP_HOST", "0.0.0.0")
mcp.settings.port = int(os.environ.get("MCP_PORT", "8002"))
mcp.settings.transport_security.enable_dns_rebinding_protection = False


def _require_db_url() -> str:
    db_url = default_db_url()
    if not db_url:
        raise ValueError("Database URL is not configured. Set RAG_USER and RAG_PWD.")
    return db_url


def _slide_resource_uri(presentation_id: str, slide_index: int) -> str:
    return f"slide://{quote(presentation_id, safe='')}/{slide_index}"


def _register_discoverable_resources() -> None:
    db_url = _require_db_url()
    with connect_db(db_url) as conn:
        recordings = list_course_recordings(conn, DEFAULT_COURSE_ID)

        catalog_payload = []
        for presentation_id in recordings:
            slides = list_slides_for_recording_rows(conn, DEFAULT_COURSE_ID, presentation_id)
            catalog_payload.append(
                {
                    "presentation_id": presentation_id,
                    "slide_count": len(slides),
                    "slides_resource_hint": f"Use the list_slides_for_recording tool with presentation_id={presentation_id!r}",
                }
            )

            for slide in slides:
                image_path = slide.get("image_path")
                slide_index = slide.get("slide_index")
                if not image_path or slide_index is None:
                    continue

                file_path = (OUTPUT_DIR / str(image_path)).resolve()
                try:
                    file_path.relative_to(OUTPUT_DIR)
                except ValueError:
                    continue
                if not file_path.is_file():
                    continue

                uri = _slide_resource_uri(presentation_id, slide_index)
                resource = FileResource(
                    uri=uri,
                    name=f"{presentation_id} slide {slide_index}",
                    title=f"{presentation_id} slide {slide_index}",
                    description=f"Slide image for {presentation_id}, slide {slide_index}",
                    mime_type="image/jpeg",
                    path=file_path,
                    is_binary=True,
                )
                mcp.add_resource(resource)

        catalog_resource = TextResource(
            uri="recordings://catalog",
            name="recordings_catalog",
            title="Recordings Catalog",
            description="Catalog of available recordings and approximate slide counts.",
            mime_type="application/json",
            text=json.dumps(catalog_payload, ensure_ascii=False, indent=2),
        )
        mcp.add_resource(catalog_resource)
        log.info("Registered MCP resources: recordings catalog plus %s concrete slide resources", sum(item["slide_count"] for item in catalog_payload))


@mcp.tool()
def list_recordings() -> list[str]:
    """List available recording/presentation names in the forestry course."""
    db_url = _require_db_url()
    with connect_db(db_url) as conn:
        return list_course_recordings(conn, DEFAULT_COURSE_ID)


@mcp.tool()
def list_slides_for_recording(presentation_id: str) -> list[dict]:
    """List available slides for a recording and return MCP resource URIs."""
    db_url = _require_db_url()
    with connect_db(db_url) as conn:
        slides = list_slides_for_recording_rows(conn, DEFAULT_COURSE_ID, presentation_id)

    return [
        {
            "presentation_id": slide["presentation_id"],
            "slide_index": slide["slide_index"],
            "timestamp_start": slide["timestamp_start"],
            "timestamp_end": slide["timestamp_end"],
            "image_path": slide["image_path"],
            "resource_uri": _slide_resource_uri(slide["presentation_id"], slide["slide_index"]),
        }
        for slide in slides
    ]


@mcp.resource("slide://{presentation_id}/{slide_index}")
def slide_resource(presentation_id: str, slide_index: str) -> bytes:
    """Read a slide image resource by presentation and slide number."""
    decoded_presentation_id = unquote(presentation_id)
    try:
        slide_number = int(slide_index)
    except ValueError as error:
        raise ValueError(f"Invalid slide index: {slide_index}") from error

    db_url = _require_db_url()
    with connect_db(db_url) as conn:
        slide = get_slide_for_recording(conn, DEFAULT_COURSE_ID, decoded_presentation_id, slide_number)

    if not slide:
        raise FileNotFoundError(f"Slide not found for presentation_id={decoded_presentation_id} slide_index={slide_number}")

    image_path = slide.get("image_path")
    if not image_path:
        raise FileNotFoundError(f"Slide image missing for presentation_id={decoded_presentation_id} slide_index={slide_number}")

    file_path = (OUTPUT_DIR / str(image_path)).resolve()
    try:
        file_path.relative_to(OUTPUT_DIR)
    except ValueError as error:
        raise ValueError(f"Invalid slide path: {file_path}") from error

    if not file_path.is_file():
        raise FileNotFoundError(f"Slide file not found: {file_path}")

    log.info("Serving slide resource %s from %s", _slide_resource_uri(decoded_presentation_id, slide_number), file_path)
    return file_path.read_bytes()


if __name__ == "__main__":
    _register_discoverable_resources()
    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")
    if transport not in {"streamable-http", "sse", "stdio"}:
        raise ValueError(f"Unsupported MCP_TRANSPORT: {transport}")

    if transport == "sse":
        mount_path = os.environ.get("MCP_MOUNT_PATH", "/mcp")
        log.info("Starting MCP server with transport=%s mount_path=%s", transport, mount_path)
        mcp.run(transport=transport, mount_path=mount_path)
    else:
        log.info("Starting MCP server with transport=%s", transport)
        mcp.run(transport=transport)
