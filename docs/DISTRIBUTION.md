# Image sources, licences and notices

The image contains the rebuilt Casdoor backend/frontend, Swagger UI and their
runtime dependencies. Casdoor's Apache licence and notices are retained.
Dependencies keep their own licences; the application licence label does not
relicense system libraries, browser bundles or fonts.

## Included distribution material

The `/licenses` directory contains:

- The integration licence and NOTICE, including required attribution.
- Source provenance identifying the Casdoor revision and applied patch series.
- Backend, frontend, font and Swagger dependency inventories and notices.
- Exact source ZIPs for covered Go modules carrying MPL notices.
- System package inventory and corresponding Alpine source recipes, patches,
  configuration and checksum-verified archives.
- Recovered original licence evidence and its provenance.

The source archives consume image download and storage space; they are inactive
files and do not start additional services. To extract them without starting
Casdoor, set `CASDOOR_IMAGE` to your local image or a verified published digest:

```sh
container=$(docker create "$CASDOOR_IMAGE")
docker cp "$container:/licenses" ./image-licenses
docker rm "$container"
```

## Licence details

The LDAP message dependency uses its author's MIT revision
`8d785c64d1c87d6fa9c95591edf9d8abc603a34c`; only its licence changed from the
previously pinned revision. The original MIT notice is included. FreeType-Go
uses its permitted FreeType License option with the required NOTICE credit.
Covered MPL modules include their checksum-verified source ZIPs alongside notices.

[swagger.lock.json](../swagger.lock.json) identifies Swagger UI 4.1.0 and the
exact assets. Missing `.LICENSE.txt` files referenced by those original bundles
are supplied with combined notices; the JavaScript is unchanged.

Some dependency archives omit a separate licence file.
[licenses/overrides.json](../licenses/overrides.json) identifies recovered originals,
hashes and source provenance. Original grants in a README or parent project
accompany full licence terms. Two npm notices come from pinned project revisions
rather than an unavailable npm `gitHead`. The `format` package includes the
author's original copyright/MIT grant and generic MIT terms; its linked licence
page was unavailable. The provenance records retain these distinctions.

[os.lock.json](../os.lock.json) identifies installed package versions, licences,
source origins and Alpine commits. The source kit includes the corresponding
APKBUILD files and sources verified against their original recipe checksums.
Packages without remote source retain their local source files. Original source
copyrights remain in the files and archives.

## Inventory and signed evidence

The builder inventories production Go imports/toolchain, frontend modules and
CSS/font dependencies, and the exact Swagger bundle's source-map dependencies.
Publication checks required notice/source coverage and installed package identity.
These checks do not constitute independent legal or security approval.

The publishing workflow attaches BuildKit's SBOM/provenance and signs a separate
SPDX inventory that includes dependencies inside compiled browser assets.
Unresolved licence metadata remains `NOASSERTION`; use the full notices as the
licence evidence. See [image verification](REGISTRY.md#verify-a-published-image)
for signature and SPDX attestation commands.

When redistributing a modified image, retain the applicable licence terms,
notices, attribution and corresponding-source obligations for its contents.
