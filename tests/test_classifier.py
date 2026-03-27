from codex_adv.classifier import classify_prompt


def test_classify_simple_fix():
    classification = classify_prompt("Fix this unit test failure")
    assert classification.task_type in {"test_help", "small_fix", "multi_file_edit"}
    assert classification.complexity_score >= 1


def test_classify_architecture_prompt():
    classification = classify_prompt("Design the system architecture for a coding router")
    assert classification.task_type == "architecture"
    assert classification.complexity_score >= 3


def test_classify_system_inspection_prompt():
    classification = classify_prompt(
        "go through my local machine and let me know "
        "if it's possible to optimize it for memory consumption"
    )
    assert classification.task_type == "system_inspection"
