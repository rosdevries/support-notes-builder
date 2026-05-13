"""Static slot HTML — content that does NOT change month to month.

These were lifted directly from the April 2026 Tessent shipped email
(``_TEST_-_Send_amends_and_approvals_to_Ros___Tessent_지원_노트_-_2026년_4월``)
which represents the "as-rendered in production" output.  Reusing this HTML
verbatim is the lowest-risk path: it preserves SFMC's content-builder
formatting, link aliases, image asset IDs, and CDN URLs that have already
shipped successfully to subscribers.

Language-aware helpers (``get_contact_body``, ``get_footnote``, ``get_footer``)
return the correct variant for the email's language so that parsing an English
.eml no longer shows Korean static defaults.
"""

# ---------------------------------------------------------------------------
# Header subscribe button — language-aware label + profile URL.
# ---------------------------------------------------------------------------

_SUBSCRIBE_LABELS = {
    "ko": "구독신청",
    "en": "Subscribe",
    "ja": "購読する",
    "zh-CN": "订阅",
    "zh-TW": "訂閱",
}

_SUBSCRIBE_PROFILE_URLS = {
    "ko": "https://account.sw.siemens.com/ko-KR/profile",
    "en": "https://account.sw.siemens.com/en-US/profile",
    "ja": "https://account.sw.siemens.com/ja-JP/profile",
    "zh-CN": "https://account.sw.siemens.com/zh-CN/profile",
    "zh-TW": "https://account.sw.siemens.com/zh-TW/profile",
}


def get_subscribe_button(language: str, subscribe_url: str = "") -> str:
    """Return the yellow Subscribe button HTML for the given language.

    ``subscribe_url`` overrides the default profile URL when set (e.g. when
    the AI extractor pulled a custom link from the .eml).
    """
    label = _SUBSCRIBE_LABELS.get(language, "Subscribe")
    url = subscribe_url.strip() or _SUBSCRIBE_PROFILE_URLS.get(language, _SUBSCRIBE_PROFILE_URLS["en"])
    return (
        '<table cellpadding="0" cellspacing="0" class="stylingblock-content-wrapper" '
        'role="presentation" style="min-width: 100%; " width="100%">'
        '<tr><td class="stylingblock-content-wrapper camarker-inner">'
        '<table align="right" border="0" cellpadding="0" cellspacing="0" '
        'style="margin: 0 auto;" role="presentation">'
        '<tr><td bgcolor="#FFE270" style="border-radius: 3px; -moz-border-radius: 3px; '
        '-webkit-border-radius: 3px; background-color: #FFE270;">'
        '<a target="_blank" class="buttonstyles" '
        'style="font-weight: 700; font-size: 11px; font-family: Arial, Helvetica, sans-serif; '
        'color: #000000; text-align: right; text-decoration: none; display: block; '
        'background-color: #FFE270; border: 1px solid #FFE270; padding: 10px; '
        'border-radius: 3px; -moz-border-radius: 3px; -webkit-border-radius: 3px;" '
        f'href="{url}" '
        'title="Subscribe" alias="Subscribe" conversion="false" data-linkto="https://">'
        f'{label}</a></td></tr></table>'
        '</td></tr></table>'
    )


# Backwards-compat constant (Korean default).
SUBSCRIBE_BUTTON_HTML = get_subscribe_button("ko")


# ---------------------------------------------------------------------------
# Section-3 contact icon: the 20×20 envelope icon (icon cell only — the
# support-centre body text lives in SECTION3_CONTACT_BODY_HTML below).
# ---------------------------------------------------------------------------

def section3_contacticon_html() -> str:
    """Return the contact icon slot HTML, using the URL from icon_config."""
    from builder import icon_config  # lazy import avoids circular dependency
    url = icon_config.get_url("contact")
    return (
        '<table cellpadding="0" cellspacing="0" class="stylingblock-content-wrapper" '
        'role="presentation" style="min-width: 100%; " width="100%">'
        '<tr><td class="stylingblock-content-wrapper camarker-inner">'
        '<table width="100%" cellspacing="0" cellpadding="0" role="presentation">'
        '<tr><td align="center">'
        f'<img alt="" height="20" width="20" src="{url}" '
        'style="display: block; padding: 0px; text-align: center; height: 20px; width: 20px; border: 0px;">'
        '</td></tr></table>'
        '</td></tr></table>'
    )

# ---------------------------------------------------------------------------
# Section-3 contact body: the support-centre copy that sits next to the icon.
# Combined with the dynamic webinar callout by slot_renderer.
# ---------------------------------------------------------------------------

_SECTION3_CONTACT_BODY = {
    "ko": (
        '<table cellpadding="0" cellspacing="0" class="stylingblock-content-wrapper" '
        'role="presentation" style="min-width: 100%; " width="100%">'
        '<tr><td class="stylingblock-content-wrapper camarker-inner">'
        '<span style="font-size:13px;">'
        '<span style="font-family:Arial,Helvetica,sans-serif;">'
        '<b>1:1 지원 및 제안은 '
        '<a alias="Support Center" conversion="false" data-linkto="https://" '
        'href="https://support.sw.siemens.com/" '
        'style="color:#000000;text-decoration:underline;" title="Support Center">'
        'Support Center</a>를 통해 문의해주세요.</b>'
        '</span></span>'
        '<br/>&nbsp;<hr/>'
        '</td></tr></table>'
    ),
    "en": (
        '<table cellpadding="0" cellspacing="0" class="stylingblock-content-wrapper" '
        'role="presentation" style="min-width: 100%; " width="100%">'
        '<tr><td class="stylingblock-content-wrapper camarker-inner">'
        '<span style="font-size:13px;">'
        '<span style="font-family:Arial,Helvetica,sans-serif;">'
        '<b>For 1:1 support and suggestions, contact us via the '
        '<a alias="Support Center" conversion="false" data-linkto="https://" '
        'href="https://support.sw.siemens.com/" '
        'style="color:#000000;text-decoration:underline;" title="Support Center">'
        'Support Center</a>.</b>'
        '</span></span>'
        '<br/>&nbsp;<hr/>'
        '</td></tr></table>'
    ),
    "ja": (
        '<table cellpadding="0" cellspacing="0" class="stylingblock-content-wrapper" '
        'role="presentation" style="min-width: 100%; " width="100%">'
        '<tr><td class="stylingblock-content-wrapper camarker-inner">'
        '<span style="font-size:13px;">'
        '<span style="font-family:Arial,Helvetica,sans-serif;">'
        '<b>1対1のサポートやご提案は、'
        '<a alias="Support Center" conversion="false" data-linkto="https://" '
        'href="https://support.sw.siemens.com/" '
        'style="color:#000000;text-decoration:underline;" title="Support Center">'
        'サポートセンター</a>からお問い合わせください。</b>'
        '</span></span>'
        '<br/>&nbsp;<hr/>'
        '</td></tr></table>'
    ),
    "zh-CN": (
        '<table cellpadding="0" cellspacing="0" class="stylingblock-content-wrapper" '
        'role="presentation" style="min-width: 100%; " width="100%">'
        '<tr><td class="stylingblock-content-wrapper camarker-inner">'
        '<span style="font-size:13px;">'
        '<span style="font-family:Arial,Helvetica,sans-serif;">'
        '<b>如需1对1支持或建议，请通过'
        '<a alias="Support Center" conversion="false" data-linkto="https://" '
        'href="https://support.sw.siemens.com/" '
        'style="color:#000000;text-decoration:underline;" title="Support Center">'
        '支持中心</a>联系我们。</b>'
        '</span></span>'
        '<br/>&nbsp;<hr/>'
        '</td></tr></table>'
    ),
    "zh-TW": (
        '<table cellpadding="0" cellspacing="0" class="stylingblock-content-wrapper" '
        'role="presentation" style="min-width: 100%; " width="100%">'
        '<tr><td class="stylingblock-content-wrapper camarker-inner">'
        '<span style="font-size:13px;">'
        '<span style="font-family:Arial,Helvetica,sans-serif;">'
        '<b>如需一對一的支援與建議，請透過以下方式聯絡我們 '
        '<a alias="Support Center" conversion="false" data-linkto="https://" '
        'href="https://support.sw.siemens.com/" '
        'style="color:#000000;text-decoration:underline;" title="Support Center">'
        'Support Center</a>.</b>'
        '</span></span>'
        '<br/>&nbsp;<hr/>'
        '</td></tr></table>'
    ),
}

# Backwards-compat constant (Korean default).
SECTION3_CONTACT_BODY_HTML = _SECTION3_CONTACT_BODY["ko"]


_EXPERT_SERIES_LOGO_HTML = (
    '<br/>\n'
    '<img alt="Expert Series" height="auto" '
    'src="https://image.s7.sfmc-content.com/lib/fe8e13737761047472/m/1/be3751f4-484d-47d5-aadf-a32c2eccbe51.png" '
    'style="display:block;border:0px;max-width:100%;" width="200">'
    '<br/>\n'
)


def get_contact_body(language: str) -> str:
    """Return the support-centre contact paragraph + Expert Series logo.

    This is the *static* part of the contact-details column.  The dynamic
    webinar callout (including the "Got more questions?" header, bullet list,
    and series link) is appended by ``slot_renderer.contact_details_default()``
    so the full default of the editable field includes everything in one place.
    """
    body = _SECTION3_CONTACT_BODY.get(language, _SECTION3_CONTACT_BODY["en"])
    return body + _EXPERT_SERIES_LOGO_HTML


# ---------------------------------------------------------------------------
# Section-3 fullwidth2: archive-links footnote (language-specific copy).
# ---------------------------------------------------------------------------

def _footnote_inner(intro: str, links: list, outro: str) -> str:
    """Build the standard footnote table from localised text + link list."""
    link_sep = ", "
    links_html = link_sep.join(
        f'<a alias="Support Notes archive ({lang_code})" conversion="false" '
        f'data-linkto="https://" href="{href}" '
        f'style="color:#000000;text-decoration:underline;" '
        f'title="Support Notes archive ({lang_code})">{label}</a>'
        for lang_code, href, label in links
    )
    body = (
        '<div style="text-align: left;">'
        '<span style="font-size:13px;"><span style="font-family:Arial,Helvetica,sans-serif;">'
        + intro + links_html + outro
        + '</span></span></div>'
    )
    return (
        '<table cellpadding="0" cellspacing="0" class="stylingblock-content-wrapper" '
        'role="presentation" style="min-width: 100%; " width="100%">'
        '<tr><td class="stylingblock-content-margin-cell" style="padding: 0; ">'
        '<table cellpadding="0" cellspacing="0" class="stylingblock-content-wrapper" '
        'role="presentation" style="background-color: transparent; min-width: 100%; " width="100%">'
        '<tr><td class="stylingblock-content-wrapper camarker-inner" style="padding: 0; ">'
        + body
        + '</td></tr></table></td></tr></table>'
    )


_ARCHIVE_LINKS_EN_KO = [
    ("EN", "https://support.sw.siemens.com/en-US/knowledge-base/MG617016", None),
    ("KO", "https://support.sw.siemens.com/ko-KR/knowledge-base/MG617016_KO", None),
]

_SECTION3_FOOTNOTE = {
    "ko": _footnote_inner(
        '<span lang="ko-kr">이전의 뉴스레터들도 확인해보세요! </span>',
        [("EN", "https://support.sw.siemens.com/en-US/knowledge-base/MG617016", "영어"),
         ("KO", "https://support.sw.siemens.com/ko-KR/knowledge-base/MG617016_KO", "한국어")],
        '<span lang="ko-kr"> 로 제공되는 자료들을 찾아보실 수 있습니다.</span>',
    ),
    "en": _footnote_inner(
        "Catch up on past Support Notes newsletters. Explore our archive in ",
        [("EN", "https://support.sw.siemens.com/en-US/knowledge-base/MG617016", "English"),
         ("KO", "https://support.sw.siemens.com/ko-KR/knowledge-base/MG617016_KO", "Korean")],
        ".",
    ),
    "ja": _footnote_inner(
        "以前のニュースレターもご覧ください — ",
        [("EN", "https://support.sw.siemens.com/en-US/knowledge-base/MG617016", "英語"),
         ("KO", "https://support.sw.siemens.com/ko-KR/knowledge-base/MG617016_KO", "韓国語")],
        "でもお読みいただけます。",
    ),
    "zh-CN": _footnote_inner(
        "查看我们以往的新闻通讯 — 提供",
        [("EN", "https://support.sw.siemens.com/en-US/knowledge-base/MG617016", "英文"),
         ("KO", "https://support.sw.siemens.com/ko-KR/knowledge-base/MG617016_KO", "韩文")],
        "版本。",
    ),
    "zh-TW": _footnote_inner(
        "Catch up on past Support Notes newsletters. Explore our archive in ",
        [("EN", "https://support.sw.siemens.com/en-US/knowledge-base/MG617016", "English"),
         ("KO", "https://support.sw.siemens.com/ko-KR/knowledge-base/MG617016_KO", "Korean")],
        ".",
    ),
}

# Backwards-compat constant (Korean default).
SECTION3_FULLWIDTH2_HTML = _SECTION3_FOOTNOTE["ko"]


def get_footnote(language: str) -> str:
    """Return the archive-links footnote for the given language."""
    return _SECTION3_FOOTNOTE.get(language, _SECTION3_FOOTNOTE["en"])


# ---------------------------------------------------------------------------
# Footer text — address, unsubscribe, copyright, privacy notice.
#
# profile_center_url is always the Support Notes account profile page.
# unsub_center_url uses the custom unsubscribe page with a lang= parameter.
# ---------------------------------------------------------------------------

_PROFILE_URL = "https://account.sw.siemens.com/en-US/profile"

_UNSUB_BASE = (
    "https://mcjp2q0rtfp7kqwfh-pnrxdqzjcq.pub.sfmc-content.com/os3qiyynjtz"
    "?jobid=%%jobid%%&listid=%%listid%%&batchid=%%_JobSubscriberBatchID%%"
    "&sk=%%_subscriberkey%%&em=%%emailaddr%%&emailname=%%emailname_%%&lang="
)

_LANG_UNSUB_CODE = {
    "en": "EN",
    "ko": "KR",
    "ja": "JP",
    "zh-CN": "CN",
    "zh-TW": "TW",
}


def get_footer(language: str) -> str:
    """Return footer HTML with hardcoded profile + language-specific unsubscribe URL."""
    lang_code = _LANG_UNSUB_CODE.get(language, "EN")
    unsub_url = _UNSUB_BASE + lang_code
    return (
        '<table cellpadding="0" cellspacing="0" class="stylingblock-content-wrapper" '
        'role="presentation" style="min-width: 100%; " width="100%">'
        '<tr><td class="stylingblock-content-wrapper camarker-inner">'
        '<div style="text-align: left;">'
        '<span style="font-size:11px;"><span style="font-family:Arial,Helvetica,sans-serif;">'
        'This email was sent to:&nbsp;%%emailaddr%%<br/>\n'
        '%%Member_Busname%%<br/>\n'
        '%%Member_Addr%% %%Member_City%%, %%Member_State%%, %%Member_PostalCode%%, %%Member_Country%%<br/>\n'
        '<a alias="Contact Us" conversion="false" data-linkto="https://" '
        'href="https://support.sw.siemens.com/en-US/" '
        'style="color:#FFFFFF;text-decoration:underline;" title="Contact Us">Contact Us</a>'
        ' | '
        f'<a alias="Update preferences" conversion="false" data-linkto="https://" '
        f'href="{_PROFILE_URL}" '
        'style="color:#FFFFFF;text-decoration:underline;" title="Update preferences">'
        'Update your preferences</a>'
        ' or '
        f'<a alias="Unsubscribe" conversion="false" data-linkto="https://" '
        f'href="{unsub_url}" '
        'style="color:#FFFFFF;text-decoration:underline;" title="Unsubscribe">unsubscribe</a>'
        '<br/>\n<br/>\n'
        'You are receiving this newsletter as you are a customer of Siemens EDA. '
        'Understand how your data is used by referring to our '
        '<a alias="Privacy Notice" conversion="false" data-linkto="https://" '
        'href="https://www.sw.siemens.com/en-US/privacy-policy/" '
        'style="color:#FFFFFF;text-decoration:underline;" title="Privacy Notice">'
        'Privacy Notice</a>. '
        'You may object to the use of your data for advertising purposes, or newsletter '
        'subscriptions at any time by '
        '<a alias="contact us" conversion="false" data-linkto="https://" '
        'href="https://support.sw.siemens.com/en-US/" '
        'style="color:#FFFFFF;text-decoration:underline;" title="contact us">'
        'contacting us</a>.<br/>\n<br/>\n'
        '&copy; 2026 Siemens Digital Industries Software. Siemens and the Siemens logo are '
        'registered trademarks of Siemens AG. All other logos, trademarks, registered '
        'trademarks or service marks used herein are the property of their respective holders.'
        '</span></span></div>'
        '</td></tr></table>'
    )


# Backwards-compat constant (Korean/EN unsubscribe default).
FOOTERTEXT_HTML = get_footer("ko")


# ---------------------------------------------------------------------------
# Empty-by-default slots
# ---------------------------------------------------------------------------
# Some slots in the SFMC template exist for layout flexibility but are
# typically empty in practice (e.g. an alternative intro speech, the
# section-3 contact-details right column, social media icons row when
# they're rendered as <img> tags within `headertitle`/`footertext`).
# We send empty strings for these and let the template's surrounding
# CSS handle the spacing.

EMPTY_SLOT_HTML = ""
