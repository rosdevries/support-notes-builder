# Slot inventory

The SFMC HTML email template `templates/support-notes-template.html` defines
24 named content slots, plus one "preheader" slot that lives inside an HTML
comment in `<head>` (the visible inbox-preview text — actual email-metadata
preheader is set via the SFMC asset's `views.html.meta.preheader`).

Each `<div data-type="slot" data-key="…">` in the template is a placeholder
that the builder fills with rendered HTML.  The slot keys below are the
authoritative list the renderer (commit 2) targets.

## Per-product, per-month — these change every send

| Slot key                           | Content                                                                                  | Notes |
| ---------------------------------- | ---------------------------------------------------------------------------------------- | ----- |
| `headertitle`                      | `TESSENT 지원 노트` / `FUNCTIONAL VERIFICATION 지원 노트`                                | Product name + language-specific suffix (`지원 노트` / `Support Notes` / `サポートノート` / `支持说明` / `支援說明`) |
| `headersubscribebuttondate`        | Date label + subscribe button link, e.g. `2026년 5월`                                    | Localised month label |
| `headerstrapline`                  | One-line product tagline                                                                 | e.g. `유용한 Tessent™ 팁과 기술이 담긴 월간 뉴스레터입니다.` |
| `section1quote`                    | Question headline for editorial 1                                                        | The teaser question |
| `section1headshot`                 | Speaker 1 photo (`<img>` to SFMC CDN URL)                                                | 120×120 PNG, green background |
| `a3d2cnhpoq`                       | Speaker 1 name & title                                                                   | Auto-named slot — speaker 1 equivalent of `section2nameandtitle` |
| `section1editorial`                | Editorial body paragraph 1                                                               | Localised |
| `section1resourcenamesleftcol`     | KBA article name (left col under editorial 1)                                            | Linked to KBA URL |
| `section1resourcenamesrightcol`    | KBA tag links (right col under editorial 1)                                              | Tag chips |
| `section2quote`                    | Question headline for editorial 2                                                        |       |
| `section2headshot`                 | Speaker 2 photo                                                                          | 120×120 PNG |
| `section2nameandtitle`             | Speaker 2 name & title                                                                   |       |
| `section2editorial`                | Editorial body paragraph 2                                                               |       |
| `section2resourcenamesleftcol`     | KBA article name (left col under editorial 2)                                            |       |
| `section2resourcenamesrightcol`    | KBA tag links (right col under editorial 2)                                              |       |
| `section3highlightrightcol`        | Upcoming live-webinar callout (date + title)                                             | Sometimes also includes Tessent training-discount promo block |
| `section3resourcesrightcol`        | Latest release version (e.g. `Tessent 2026.1` → `Tessent 2026.1-p1`)                     | Multiple lines for FV (5 components) |

Note on the auto-key `a3d2cnhpoq`: this looks like an SFMC content-block
auto-generated key for what should logically be `section1nameandtitle`. The
template keeps it as-is to avoid breaking existing draft emails. The
renderer treats it semantically as "speaker-1 name & title".

## Static across products and months — embed once, never touch

| Slot key                  | Content                                                                                  |
| ------------------------- | ---------------------------------------------------------------------------------------- |
| `introspeel`              | "Get help with…" generic intro paragraph                                                 |
| `section3fullwidth`       | Static announcement block (1:1 support / Support Center link)                            |
| `section3contacticon`     | Envelope icon                                                                            |
| `section3contactdetails`  | Contact email / Support Center URL                                                       |
| `section3fullwidth2`      | Static footnote                                                                          |
| `footersocialmediaicons`  | LinkedIn / X / YouTube icons                                                              |
| `footertext`              | Address, unsubscribe, copyright, privacy notice                                          |
| `preheader`               | The "view this email in browser" link (currently HTML-commented out in template)         |

## Tessent-only addition

The Tessent emails carry an extra promo block inside `section3highlightrightcol`:

> 프로모션 코드 "ExpertSeries"를 사용하여 트레이닝을 등록하시면 정가 대비 25%
> 할인 혜택을 받으실 수 있습니다.

Functional Verification does not. The renderer will treat this as a
product-aware optional fragment.

## Subject line

Not a slot — set on the SFMC asset's `views.html.meta.subject`. Format
varies by language:

* `ko`:    `{Product} 지원 노트 - 2026년 5월`
* `en`:    `{Product} Support Notes - May 2026`
* `ja`:    `{Product} サポートノート - 2026年5月`
* `zh-CN`: `{Product} 支持说明 - 2026年5月`
* `zh-TW`: `{Product} 支援說明 - 2026年5月`
