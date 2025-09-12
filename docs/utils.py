"""Utility functions for Google Docs tools."""

import io
import logging
import zipfile
import xml.etree.ElementTree as ET
from typing_extensions import List, Optional

logger = logging.getLogger(__name__)


def extract_office_xml_text(file_bytes: bytes, mime_type: str) -> Optional[str]:
    """
    Very light-weight XML scraper for Word, Excel, PowerPoint files.
    Returns plain-text if something readable is found, else None.
    No external deps – just std-lib zipfile + ElementTree.
    """
    shared_strings: List[str] = []
    ns_excel_main = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'

    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            targets: List[str] = []
            # Map MIME → iterable of XML files to inspect
            if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                targets = ["word/document.xml"]
            elif mime_type == "application/vnd.openxmlformats-officedocument.presentationml.presentation":
                targets = [n for n in zf.namelist() if n.startswith("ppt/slides/slide")]
            elif mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
                targets = [n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and "drawing" not in n]
                # Attempt to parse sharedStrings.xml for Excel files
                try:
                    shared_strings_xml = zf.read("xl/sharedStrings.xml")
                    shared_strings_root = ET.fromstring(shared_strings_xml)
                    for si_element in shared_strings_root.findall(f"{{{ns_excel_main}}}si"):
                        text_parts = []
                        # Find all <t> elements, simple or within <r> runs, and concatenate their text
                        for t_element in si_element.findall(f".//{{{ns_excel_main}}}t"):
                            if t_element.text:
                                text_parts.append(t_element.text)
                        shared_strings.append("".join(text_parts))
                except KeyError:
                    logger.info("No sharedStrings.xml found in Excel file (this is optional).")
                except ET.ParseError as e:
                    logger.error(f"Error parsing sharedStrings.xml: {e}")
                except Exception as e: # Catch any other unexpected error during sharedStrings parsing
                    logger.error(f"Unexpected error processing sharedStrings.xml: {e}", exc_info=True)
            else:
                return None

            pieces: List[str] = []
            for member in targets:
                try:
                    xml_content = zf.read(member)
                    xml_root = ET.fromstring(xml_content)
                    member_texts: List[str] = []

                    if mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
                        for cell_element in xml_root.findall(f".//{{{ns_excel_main}}}c"): # Find all <c> elements
                            value_element = cell_element.find(f"{{{ns_excel_main}}}v") # Find <v> under <c>

                            # Skip if cell has no value element or value element has no text
                            if value_element is None or value_element.text is None:
                                continue

                            cell_type = cell_element.get('t')
                            if cell_type == 's':  # Shared string
                                try:
                                    ss_idx = int(value_element.text)
                                    if 0 <= ss_idx < len(shared_strings):
                                        member_texts.append(shared_strings[ss_idx])
                                    else:
                                        logger.warning(f"Invalid shared string index {ss_idx} in {member}. Max index: {len(shared_strings)-1}")
                                except ValueError:
                                    logger.warning(f"Non-integer shared string index: '{value_element.text}' in {member}.")
                            else:  # Direct value (number, boolean, inline string if not 's')
                                member_texts.append(value_element.text)
                    else:  # Word or PowerPoint
                        for elem in xml_root.iter():
                            # For Word: <w:t> where w is "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                            # For PowerPoint: <a:t> where a is "http://schemas.openxmlformats.org/drawingml/2006/main"
                            if elem.tag.endswith("}t") and elem.text: # Check for any namespaced tag ending with 't'
                                cleaned_text = elem.text.strip()
                                if cleaned_text: # Add only if there's non-whitespace text
                                     member_texts.append(cleaned_text)

                    if member_texts:
                        pieces.append(" ".join(member_texts)) # Join texts from one member with spaces

                except ET.ParseError as e:
                    logger.warning(f"Could not parse XML in member '{member}' for {mime_type} file: {e}")
                except Exception as e:
                    logger.error(f"Error processing member '{member}' for {mime_type}: {e}", exc_info=True)
                    # continue processing other members

            if not pieces: # If no text was extracted at all
                return None

            # Join content from different members (sheets/slides) with double newlines for separation
            text = "\n\n".join(pieces).strip()
            return text or None # Ensure None is returned if text is empty after strip

    except zipfile.BadZipFile:
        logger.warning(f"File is not a valid ZIP archive (mime_type: {mime_type}).")
        return None
    except ET.ParseError as e: # Catch parsing errors at the top level if zipfile itself is XML-like
        logger.error(f"XML parsing error at a high level for {mime_type}: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to extract office XML text for {mime_type}: {e}", exc_info=True)
        return None