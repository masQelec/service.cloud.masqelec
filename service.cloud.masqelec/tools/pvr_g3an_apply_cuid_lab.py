#!/usr/bin/env python3
"""G3-AN source candidate for a SEPARATE G3-AL-patched Tvheadend worktree.

Never runs make, never starts services, never touches Tvheadend runtime state.
Operator must separately review git diff, compile and gate in fresh isolated lab.
"""
import argparse
from pathlib import Path
import sys

def replace_one(s, old, new, label):
    if s.count(old) != 1:
        raise RuntimeError("SOURCE_ANCHOR_MISMATCH_" + label)
    return s.replace(old, new, 1)

def patch(root, dry_run):
    auto = root / "src/input/mpegts/iptv/iptv_auto.c"
    mux = root / "src/input/mpegts/iptv/iptv_mux.c"
    head = root / "src/input/mpegts/iptv/iptv_private.h"
    original = {p: p.read_text() for p in (auto, mux, head)}
    if "G3-AL laboratory candidate" not in original[auto]:
        raise RuntimeError("G3AL_BASE_PATCH_MISSING")
    data = dict(original)

    data[head] = replace_one(data[head],
        "  char                 *mm_iptv_url_cmpid;\n",
        "  char                 *mm_iptv_url_cmpid;\n"
        "  char                 *mm_iptv_cuid; /* stable per-network playlist key, optional */\n",
        "PRIVATE_CUID")

    data[mux] = replace_one(data[mux],
        '      .id       = "iptv_url_cmpid",\n'
        '      .name     = N_("URL for comparison"),\n'
        '      .off      = offsetof(iptv_mux_t, mm_iptv_url_cmpid),\n'
        '      .opts     = PO_MULTILINE | PO_HIDDEN | PO_NOUI,\n'
        '    },\n',
        '      .id       = "iptv_url_cmpid",\n'
        '      .name     = N_("URL for comparison"),\n'
        '      .off      = offsetof(iptv_mux_t, mm_iptv_url_cmpid),\n'
        '      .opts     = PO_MULTILINE | PO_HIDDEN | PO_NOUI,\n'
        '    },\n'
        '    {\n'
        '      .type     = PT_STR,\n'
        '      .id       = "iptv_cuid",\n'
        '      .name     = N_("Stable playlist channel identity"),\n'
        '      .off      = offsetof(iptv_mux_t, mm_iptv_cuid),\n'
        '      .opts     = PO_HIDDEN | PO_NOUI,\n'
        '    },\n',
        "MUX_CLASS_CUID")
    data[mux] = replace_one(data[mux],
        "  free(im->mm_iptv_url_cmpid);\n",
        "  free(im->mm_iptv_url_cmpid);\n"
        "  free(im->mm_iptv_cuid);\n", "MUX_FREE_CUID")

    helper = r'''
/*
 * G3-AN candidate, synthetic HTTP playlist laboratory only:
 * Preflight CUID uniqueness and active-mux URL changes BEFORE mutating any mux.
 * No name-based adoption, no silent duplicate CUID or ambiguous URL mapping.
 */
static int
g3an_valid_cuid(const char *s)
{
  size_t n;
  if (s == NULL || !*s) return 0;
  for (n = 0; s[n]; n++) {
    if (n >= 128 ||
        !((s[n] >= 'a' && s[n] <= 'z') ||
          (s[n] >= 'A' && s[n] <= 'Z') ||
          (s[n] >= '0' && s[n] <= '9') ||
          s[n] == '-' || s[n] == '_' || s[n] == '.'))
      return 0;
  }
  return 1;
}

static int
g3an_preflight(iptv_network_t *in, htsmsg_t *items)
{
  htsmsg_field_t *f, *g;
  htsmsg_t *item, *other;
  const char *cuid, *other_cuid, *url;
  mpegts_mux_t *mm;
  iptv_mux_t *im;
  int matches, legacy;
  HTSMSG_FOREACH(f, items) {
    item = htsmsg_field_get_map(f);
    if (!item) continue;
    cuid = htsmsg_get_str(item, "CUID");
    if (cuid) {
      if (!g3an_valid_cuid(cuid)) {
        tvherror(LS_IPTV, "G3-AN invalid CUID in playlist");
        return -1;
      }
      HTSMSG_FOREACH(g, items) {
        if (g == f) break;
        other = htsmsg_field_get_map(g);
        if (!other) continue;
        other_cuid = htsmsg_get_str(other, "CUID");
        if (other_cuid && strcmp(cuid, other_cuid) == 0) {
          tvherror(LS_IPTV, "G3-AN duplicate CUID, refusing playlist");
          return -1;
        }
      }
      matches = 0;
      legacy = 0;
      LIST_FOREACH(mm, &in->mn_muxes, mm_network_link) {
        im = (iptv_mux_t *)mm;
        if (im->mm_iptv_cuid && strcmp(im->mm_iptv_cuid, cuid) == 0)
          matches++;
        else if (!im->mm_iptv_cuid &&
                 (url = htsmsg_get_str(item, "m3u-url")) &&
                 strcmp(im->mm_iptv_url_sane ?: (im->mm_iptv_url ?: ""), url) == 0)
          legacy++;
      }
      if (matches > 1 || (!matches && legacy > 1)) {
        tvherror(LS_IPTV, "G3-AN ambiguous existing CUID/URL mapping");
        return -1;
      }
      /* Reject changes to a playing mux; wait until no active stream. */
      LIST_FOREACH(mm, &in->mn_muxes, mm_network_link) {
        im = (iptv_mux_t *)mm;
        if (im->mm_iptv_cuid && strcmp(im->mm_iptv_cuid, cuid) == 0 &&
            im->mm_active &&
            (url = htsmsg_get_str(item, "m3u-url")) &&
            strcmp(im->mm_iptv_url_sane ?: (im->mm_iptv_url ?: ""), url) != 0) {
          tvhinfo(LS_IPTV, "G3-AN URL change deferred for active stream");
          return -1;
        }
      }
    }
  }
  return 0;
}
'''
    data[auto] = replace_one(data[auto],
        "static void\niptv_auto_network_process_m3u_item(",
        helper + "\nstatic void\niptv_auto_network_process_m3u_item(",
        "AUTO_HELPER")
    data[auto] = replace_one(data[auto],
        '  const char *url, *url2, *name, *logo, *epgid, *tags;\n',
        '  const char *url, *url2, *name, *logo, *epgid, *tags, *cuid;\n'
        '  iptv_mux_t *by_cuid = NULL;\n',
        "AUTO_DECL")
    data[auto] = replace_one(data[auto],
        '  url = htsmsg_get_str(item, "m3u-url");\n',
        '  url = htsmsg_get_str(item, "m3u-url");\n'
        '  cuid = htsmsg_get_str(item, "CUID");\n',
        "AUTO_CUID")
    data[auto] = replace_one(data[auto],
        '  LIST_FOREACH(mm, &in->mn_muxes, mm_network_link) {\n'
        '    im = (iptv_mux_t *)mm;\n'
        '    if (strcmp(im->mm_iptv_url_cmpid ?: (im->mm_iptv_url ?: ""), url2) == 0) {\n',
        '  /* CUID takes precedence. URL matching only adopts a legacy mux with\n'
        '   * no CUID, never a mux already belonging to another stable identity. */\n'
        '  if (cuid) {\n'
        '    LIST_FOREACH(mm, &in->mn_muxes, mm_network_link) {\n'
        '      im = (iptv_mux_t *)mm;\n'
        '      if (im->mm_iptv_cuid && strcmp(im->mm_iptv_cuid, cuid) == 0) {\n'
        '        by_cuid = im;\n'
        '        break;\n'
        '      }\n'
        '    }\n'
        '  }\n'
        '  LIST_FOREACH(mm, &in->mn_muxes, mm_network_link) {\n'
        '    im = (iptv_mux_t *)mm;\n'
        '    if ((by_cuid && im == by_cuid) ||\n'
        '        (!by_cuid && !im->mm_iptv_cuid &&\n'
        '         strcmp(im->mm_iptv_url_cmpid ?: (im->mm_iptv_url ?: ""), url2) == 0)) {\n'
        '      if (cuid && !im->mm_iptv_cuid) {\n'
        '        im->mm_iptv_cuid = strdup(cuid);\n'
        '        idnode_changed(&im->mm_id);\n'
        '      }\n'
        '      if (by_cuid && strcmp(im->mm_iptv_url_cmpid ?: "", url2) != 0) {\n'
        '        /* Do not change a currently playing stream in-place. */\n'
        '        if (im->mm_active) goto end;\n'
        '        iptv_url_set(&im->mm_iptv_url, &im->mm_iptv_url_sane,\n'
        '                     url, 1, 1);\n'
        '        free(im->mm_iptv_url_cmpid);\n'
        '        im->mm_iptv_url_cmpid = strdup(url2);\n'
        '        idnode_changed(&im->mm_id);\n'
        '      }\n',
        "AUTO_MATCH")
    data[auto] = replace_one(data[auto],
        '  htsmsg_add_str(conf, "iptv_url_cmpid", url2);\n',
        '  htsmsg_add_str(conf, "iptv_url_cmpid", url2);\n'
        '  if (cuid) htsmsg_add_str(conf, "iptv_cuid", cuid);\n',
        "AUTO_CREATE")
    data[auto] = replace_one(data[auto],
        '  items = htsmsg_get_list(m, "items");\n'
        '  if (items) {\n',
        '  items = htsmsg_get_list(m, "items");\n'
        '  if (items && g3an_preflight(in, items)) {\n'
        '    htsmsg_destroy(m);\n'
        '    return -1;\n'
        '  }\n'
        '  if (items) {\n',
        "AUTO_PREFLIGHT")

    print("G3AN_SOURCE_ANCHORS=PASS", flush=True)
    if dry_run:
        print("G3AN_APPLY=DRY_RUN", flush=True)
        return
    # Write only after all anchors match, using rename in same directory.
    for path, text in data.items():
        tmp = path.with_name(path.name + ".g3an-tmp")
        if tmp.exists():
            raise RuntimeError("TEMP_FILE_EXISTS_" + tmp.name)
        try:
            with tmp.open("x") as f:
                f.write(text)
            tmp.chmod(path.stat().st_mode & 0o777)
            tmp.replace(path)
        finally:
            if tmp.exists():
                tmp.unlink()
    print("G3AN_SOURCE_APPLIED=YES", flush=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("tree", type=Path)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    root = args.tree.resolve()
    if root != Path("/home/ubuntu/tvheadend-g3an-upstream"):
        raise RuntimeError("WRONG_SOURCE_TREE")
    if not (root / ".git").exists():
        raise RuntimeError("NOT_GIT_CHECKOUT")
    patch(root, not args.apply)

if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as e:
        print("G3AN=BLOCKED_" + str(e), file=sys.stderr)
        sys.exit(2)
