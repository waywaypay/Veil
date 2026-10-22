"""Whether a stretch of Korean the tagger marked as a name could be one.

The tagger (deerpark-PII-edge) was never trained on Korean, and in Hangul it marks ordinary words as names: "투어",
"의도를", "참가자 명단에는".  Its scores don't tell those from real names, so they are judged by their words instead.
A Hangul word is an everyday one, and no name, when it is:

* a verb or adjective form ("확정되면", "부탁드리며", "생물학적");
* a word listed in wordfreq's Korean list at a Zipf frequency of 3.5 or more, once a particle is taken off ("정보는" is
  "정보" and "는"; a particle must be the form its word takes, so "지나은" is not "지나" and "은"), or made of listed
  words ("사회보장" is "사회" and "보장"), or a listed word with a suffix ("계획서", "응답자");
* a role with an honorific ("선생님", "고객님"), where another word with one ("지연님") is a person.

A name followed by "is" ("주찬우이며") is judged without it.  A three-syllable word that starts with a common surname
has a full name's shape ("함선율", "안도율"), so it counts as everyday only when listed whole, or when it is a very
common word and a suffix that seldom ends a given name ("계획서", "제안서"; not "이리안", "기지후").  A span is a name
if any of its Hangul words is not everyday, if it holds a word in other letters ("yang 종혁", "田中太郎"), or if it is
a nickname with digits ("구름303").

What this costs: a name wordfreq lists (a public figure's, "노무현"; or a given name that is also a word, "서연"), a
surname alone ("김"), and a town the tagger took for a name ("여수시", which veil leaves visible anyway) are no longer
hidden.  benchmarks/korean_names.md has the figures.

wordfreq (the tagger extra) has the frequencies; without it only the verb forms, honorifics and length are judged.
Its Korean words are mecab's pieces of words, which is why compounds are split."""
from __future__ import annotations

import math
import re
from functools import lru_cache

ZIPF = 3.5          # a word this common is an everyday one
ZIPF_PREFIX = 4.5   # how common the first two syllables of a surname-shaped word must be to make it a word and a suffix

HANGUL = re.compile(r"[\uac00-\ud7a3]")
_HANGUL_WORD = re.compile(r"[\uac00-\ud7a3]+")
_OTHER_LETTERS = re.compile(r"[^\W\d_\uac00-\ud7a3]{2,}")   # a name in Latin letters, hanja or kana
_HANDLE = re.compile(r"[\uac00-\ud7a3]+\d")                  # a nickname: "구름303"
_COPULA = re.compile(r"(?:이며|이고|이다|입니다|이에요|이었다|이라는|이라고)$")
# particles and honorifics that end a word, longest first
_PARTICLES = sorted("""님께서 님께 님의 님은 님이 님을 님과 님 씨의 씨는 씨가 씨 께서는 께서 에서부터 으로부터 에게서 에서는 에서도 에서
에게는 에게 한테 으로서 으로써 으로는 으로 로서 로써 로는 로 에는 에도 에 까지 부터 처럼 보다 이나 이랑 와는 과는 와 과 은 는 이 가 을 를 의
도 만""".split(), key=len, reverse=True)
# the forms of a particle that follow a consonant, and those that follow a vowel
_AFTER_CONSONANT = frozenset("은 이 을 과 과는 으로 으로서 으로써 으로는 으로부터 이나 이랑".split())
_AFTER_VOWEL = frozenset("는 가 를 와 와는 로 로서 로써 로는".split())
_VERBAL = re.compile(r"(?:다|니다|요|시오|세요|며|면서|지만|는데|니까|도록|하고|하는|하며|하여|해서|하면|해|했|했고|된|될|되|할|한다|되는|되어|"
                     r"되면|된다|있는|없는|주시|주시면|주시고|드리|드리며|드리니|하신|하시는|하고자|고자|합니다|습니다|겠|하기|하실|적|적인|적으로|"
                     r"적이고)$")
_SUFFIXES = tuple("""자 적 성 화 식 용 비 금 서 증 률 율 원 인 가 사 소 처 장 부 실 팀 별 간 상 하 내 외 중 후 전 시 물 표 일 명 주 값 록 문
안 단 품 료 액 량 지 회 권 계 도 법 제 형 력 감 점""".split())
_HONORIFIC = re.compile(r"^(.+?)(?:님|씨)(?:께서는|께서|께|의|은|는|이|가|을|를|과|와|도)?$")
# who an honorific can follow without being a name
_ROLES = frozenset("""선생 교수 고객 회원 사장 부장 과장 차장 팀장 대리 실장 원장 대표 이사 회장 박사 기사 작가 감독 의사 간호사 환자 손님
학생 부모 형 누나 언니 오빠 어머 아버 어머니 아버지 할머니 할아버지 남성 여성 신청자 담당자 관리자 참가자 응답자 귀하 여러분 소비자
사용자 이용자 판사 검사 변호사 기자 목사 신부 스님 주무관 위원 의원 장관 총장 학장 소장 국장 반장 선배 후배 동료 친구 주임 사원 매니저
코치 강사 멘토 멘티 조합원 후원자 보호자 수강생 입주민 주민 직원 상담사 상담원 엄마 아빠 아저씨 아주머니 이모 삼촌 사모 형님""".split())
# syllables that often end a given name, so no suffix in a word with a full name's shape ("이리안", "기지후")
_NAME_ENDINGS = frozenset("안 후 인 율 원 성 주 하 지 도 연 민 현 진 영 희 수 호 준 윤 우 은 아 이 빈 린 경 정 석 혁 훈 나 미 혜".split())
_SURNAMES = frozenset("""김 이 박 최 정 강 조 윤 장 임 한 오 서 신 권 황 안 송 류 유 전 홍 고 문 양 손 배 백 허 남 심 노 하 곽 성 차 주 우 구 민
나 진 지 엄 채 원 천 방 공 현 함 변 염 여 추 도 소 석 선 설 마 길 연 위 표 명 기 반 왕 금 옥 육 인 맹 제 모 탁 국 어 은 편 용 예 경 봉 사
부 가 복 태 목 형 계 피 두 감 음 빈 동 온 호 범 좌 팽 승 간 상 시 갈 단 견 당 화 창 옹 순 대 묵 운 근 판 라 저 초 해 뢰 학 묘 영 개 미 아
평""".split())


@lru_cache(maxsize=1)
def _frequencies() -> dict[str, float]:
    try:
        import wordfreq
    except ImportError:
        return {}
    return wordfreq.get_frequency_dict("ko")


def _zipf(word: str) -> float:
    f = _frequencies().get(word)
    return math.log10(f) + 9 if f else 0.0


def _closed(syllable: str) -> bool:
    """Whether a Hangul syllable ends in a consonant (has a batchim)."""
    return (ord(syllable) - 0xAC00) % 28 != 0


def _stems(word: str) -> list[str]:
    """The word, and the word without each particle or honorific that can end it.  A particle with two forms must be
    the one its word takes: "정보는" is "정보" and "는", but "지나은" is no "지나" with "은" (that would be "지나는")."""
    out = [word]
    for p in _PARTICLES:
        stem = word[:-len(p)]
        if not word.endswith(p) or not stem:
            continue
        if p in _AFTER_CONSONANT and not _closed(stem[-1]) or p in _AFTER_VOWEL and _closed(stem[-1]) and \
                not (p.startswith("로") and (ord(stem[-1]) - 0xAC00) % 28 == 8):   # 로 also follows ㄹ
            continue
        out.append(stem)
    return out


def _listed(stem: str) -> bool:
    """A common word, a run of common words of two syllables or more, or a common word and a suffix."""
    if _zipf(stem) >= ZIPF:
        return True
    n = len(stem)
    ends = [True] + [False] * n
    for i in range(n):
        if ends[i]:
            for j in range(i + 2, n + 1):
                if _zipf(stem[i:j]) >= ZIPF:
                    ends[j] = True
    if ends[n]:
        return True
    return n >= 3 and stem.endswith(_SUFFIXES) and _listed(stem[:-1])


def everyday(word: str) -> bool:
    """Whether a run of Hangul is an ordinary word rather than (part of) a name."""
    m = _HONORIFIC.match(word)
    if m:
        role = m.group(1)
        return role in _ROLES or any(role.endswith(r) for r in _ROLES if len(r) >= 2) or len(role) > 4
    copula = _COPULA.search(word)
    if copula and copula.start() >= 2:   # "주찬우이며" is 주찬우 and "is"
        return everyday(word[:copula.start()])
    if len(word) >= 2 and _VERBAL.search(word):
        return True
    for stem in _stems(word):
        if len(stem) == 3 and stem[0] in _SURNAMES:   # a full name's shape
            if _zipf(stem) >= ZIPF or (stem.endswith(_SUFFIXES) and stem[-1] not in _NAME_ENDINGS and
                                       _zipf(stem[:2]) >= ZIPF_PREFIX):
                return True
        elif _listed(stem):
            return True
    return len(word) > 6


def could_be_name(text: str) -> bool:
    """Whether a span the tagger marked as a name could be one: text without Hangul always could."""
    words = _HANGUL_WORD.findall(text)
    if not words or _OTHER_LETTERS.search(text) or _HANDLE.search(text):
        return True
    return not all(everyday(w) for w in words)
