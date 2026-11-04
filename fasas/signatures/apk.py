"""
Lettura minima di un APK Android: nome del pacchetto e versione dal file AndroidManifest.xml (formato XML binario
di Android). Solo libreria standard, così la CI dell'app la prova sull'APK appena compilato:

    python3 fasas/signatures/apk.py app-release.apk
"""
import struct
import sys
import zipfile

ANDROID_NS = "http://schemas.android.com/apk/res/android"
_RES_IDS = {0x0101021B: "versionCode", 0x0101021C: "versionName"}
_CHUNK_STRINGS, _CHUNK_RESOURCE_MAP, _CHUNK_START_ELEMENT = 0x0001, 0x0180, 0x0102
_TYPE_STRING, _TYPE_INT_DEC, _TYPE_INT_HEX, _TYPE_BOOLEAN = 0x03, 0x10, 0x11, 0x12
_RES_DEBUGGABLE = 0x0101000F
MAX_MANIFEST = 4 * 1024 * 1024


class ApkError(Exception):
    pass


def _strings(data, offset):
    count, _styles, flags, strings_start = struct.unpack_from("<IIII", data, offset + 8)
    utf8 = bool(flags & 0x100)
    offsets = struct.unpack_from(f"<{count}I", data, offset + 28)
    base = offset + strings_start
    result = []
    for start in offsets:
        pos = base + start
        if utf8:
            pos += 2 if data[pos] & 0x80 else 1                      # lunghezza in caratteri
            length = data[pos]
            if length & 0x80:
                length = ((length & 0x7F) << 8) | data[pos + 1]
                pos += 2
            else:
                pos += 1
            result.append(data[pos:pos + length].decode("utf-8", "replace"))
        else:
            length = struct.unpack_from("<H", data, pos)[0]
            if length & 0x8000:
                length = ((length & 0x7FFF) << 16) | struct.unpack_from("<H", data, pos + 2)[0]
                pos += 4
            else:
                pos += 2
            result.append(data[pos:pos + 2 * length].decode("utf-16-le", "replace"))
    return result


def parse_manifest(data):
    """{"package", "versionCode", "versionName", "debuggable"} dal manifest binario."""
    if len(data) < 8 or struct.unpack_from("<H", data, 0)[0] != 0x0003:
        raise ApkError("AndroidManifest.xml non è nel formato binario di Android.")
    strings, resource_ids, pos, manifest = [], [], 8, None
    while pos + 8 <= len(data):
        chunk_type, header_size, size = struct.unpack_from("<HHI", data, pos)
        if size < 8 or pos + size > len(data):
            raise ApkError("Manifest danneggiato.")
        if chunk_type == _CHUNK_STRINGS:
            strings = _strings(data, pos)
        elif chunk_type == _CHUNK_RESOURCE_MAP:
            resource_ids = list(struct.unpack_from(f"<{(size - header_size) // 4}I", data, pos + header_size))
        elif chunk_type == _CHUNK_START_ELEMENT:
            _ns, name, attr_start, attr_size, attr_count = struct.unpack_from("<iIHHH", data, pos + 16)
            if strings[name] == "application" and manifest is not None:
                manifest["debuggable"] = False
                for i in range(attr_count):
                    a = pos + 16 + attr_start + i * attr_size
                    _ans, aname, _raw, _size, _res0, dtype, value = struct.unpack_from("<iIiHBBI", data, a)
                    rid = resource_ids[aname] if aname < len(resource_ids) else None
                    if rid == _RES_DEBUGGABLE or strings[aname] == "debuggable":
                        manifest["debuggable"] = dtype == _TYPE_BOOLEAN and value != 0
                return manifest
            if strings[name] == "manifest":
                info = {}
                for i in range(attr_count):
                    a = pos + 16 + attr_start + i * attr_size
                    _ans, aname, raw, _size, _res0, dtype, value = struct.unpack_from("<iIiHBBI", data, a)
                    key = _RES_IDS.get(resource_ids[aname]) if aname < len(resource_ids) else None
                    key = key or strings[aname]
                    if dtype == _TYPE_STRING:
                        info[key] = strings[value if raw < 0 else raw]
                    elif dtype in (_TYPE_INT_DEC, _TYPE_INT_HEX):
                        info[key] = value
                    elif raw >= 0:
                        info[key] = strings[raw]
                if "package" not in info or "versionCode" not in info:
                    raise ApkError("Nel manifest mancano il nome del pacchetto o la versione.")
                manifest = {"package": info["package"], "versionCode": int(info["versionCode"]),
                            "versionName": str(info.get("versionName", "")), "debuggable": False}
        pos += size
    if manifest is None:
        raise ApkError("Elemento <manifest> non trovato.")
    return manifest


def read_apk(file):
    """file: percorso o oggetto file di un APK."""
    try:
        with zipfile.ZipFile(file) as apk:
            info = apk.getinfo("AndroidManifest.xml")
            if info.file_size > MAX_MANIFEST:
                raise ApkError("Manifest troppo grande.")
            return parse_manifest(apk.read(info))
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ApkError("Non è un'app Android (APK) valida.") from exc
    except (struct.error, IndexError) as exc:
        raise ApkError("Manifest dell'APK non leggibile.") from exc


if __name__ == "__main__":
    for path in sys.argv[1:]:
        print(path, read_apk(path))
