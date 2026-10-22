import pytest

from veil.hangul import could_be_name, everyday
from veil.tagged import merged, vetted


@pytest.mark.parametrize("words", ["투어", "의도를", "참가자 명단에는", "체계적이고", "확정되면", "부탁드리며", "사회보장번호", "계획서에",
                                   "제안서는", "응답자", "선생님", "고객님께", "현재", "저희", "개인정보 보호를", "이번 회의는"])
def test_everyday_korean_is_no_name(words):
    assert not could_be_name(words)


@pytest.mark.parametrize("name", ["김민수", "박지성", "장동건", "황보람", "함선율", "안도율", "지훈", "민준", "지연님", "양 혜숙",
                                  "피고인 장동건는", "yang 종혁", "Trove님께"])
def test_korean_names_stay_names(name):
    assert could_be_name(name)


def test_a_role_with_an_honorific_is_everyday_and_a_name_with_one_is_not():
    assert everyday("교수님께서는") and everyday("담당자님의")
    assert not everyday("민준님") and not everyday("상훈씨")


def test_text_without_hangul_is_untouched():
    assert could_be_name("Maria Lopez") and could_be_name("Itinerary")


def test_vetted_drops_only_korean_names_of_everyday_words():
    text = "현지 가이드 김민수 님과 투어 전 인사를 나누겠습니다. Call Maria Lopez on 0412 555 019."
    at = lambda s: (text.index(s), text.index(s) + len(s))   # noqa: E731
    found = [(*at("김민수"), "NAME", 0.6), (*at("투어"), "NAME", 0.5), (*at("인사를"), "NAME", 0.4),
             (*at("Maria Lopez"), "NAME", 0.9), (*at("0412 555 019"), "PHONE", 0.9)]
    kept = [text[s:e] for s, e, _, _ in vetted(found, text)]
    assert kept == ["김민수", "Maria Lopez", "0412 555 019"]
    assert [text[s:e] for s, e, _, _ in merged(found, text)] == kept


@pytest.mark.parametrize("name", ["담당자는 주찬우이며", "기록 응답자: 지나은", "구름303", "외국인 피의자 田中太郎", "이리안", "기지후"])
def test_what_looks_like_an_ordinary_word_but_holds_a_name(name):
    assert could_be_name(name)


def test_a_particle_is_taken_off_only_in_the_form_its_word_takes():
    assert everyday("정보는") and everyday("기타이며")
    assert not everyday("지나은")
