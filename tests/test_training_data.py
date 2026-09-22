import json

import pytest

from training.dataset import FIELDS, digest, group_key, prepare, split_for, validated_examples, reviewed_rows


def test_drafts_never_become_training_labels(tmp_path):
    batch = tmp_path / 'batch_0001'
    batch.mkdir()
    text = 'Candidate candidate@example.com'
    row = {'id': 'one', 'text': text, 'text_hash': digest(text.lower().encode()),
           'review_status': 'pending', 'answers': None}
    (batch / 'examples.jsonl').write_text(json.dumps(row), encoding='utf-8')
    assert validated_examples(tmp_path) == ([], [])
    row.update(review_status='approved', reviewed_by='')
    (batch / 'examples.jsonl').write_text(json.dumps(row), encoding='utf-8')
    with pytest.raises(ValueError, match='reviewer'):
        validated_examples(tmp_path)
    row.update(reviewed_by='test-reviewer', answers={key: '' for key in FIELDS})
    (batch / 'examples.jsonl').write_text(json.dumps(row), encoding='utf-8')
    training, validation = validated_examples(tmp_path)
    assert len(training) + len(validation) == 1


def test_same_email_keeps_cv_versions_in_same_split():
    assert group_key('First CV person@example.com') == group_key('Updated CV PERSON@example.com')
    assert split_for(group_key('First CV person@example.com')) == split_for(group_key('Updated person@example.com'))


def test_review_sidecar_cannot_replace_source(tmp_path):
    path = tmp_path / 'examples.jsonl'
    path.write_text(json.dumps({'id': 'one', 'text': 'original', 'review_status': 'pending'}), encoding='utf-8')
    reviews = tmp_path / 'reviews.json'
    reviews.write_text(json.dumps({'one': {'review_status': 'needs_review'}}), encoding='utf-8')
    assert reviewed_rows(path)[0]['review_status'] == 'needs_review'
    assert json.loads(path.read_text())['review_status'] == 'pending'
    reviews.write_text(json.dumps({'one': {'text': 'replacement'}}), encoding='utf-8')
    with pytest.raises(ValueError, match='cannot change source'):
        reviewed_rows(path)


def test_random_batches_exclude_previously_selected_files(tmp_path, monkeypatch):
    from cv_parser.extractors import ExtractedText
    from cv_parser.schema import CandidateRecord
    import training.dataset as dataset
    source, output = tmp_path / 'source', tmp_path / 'output'
    source.mkdir()
    for index in range(5):
        (source / f'{index}.pdf').write_bytes(f'CV {index}'.encode())
    monkeypatch.setattr(dataset, 'extract_file', lambda name, content, **kwargs: ExtractedText(content.decode(), []))
    monkeypatch.setattr(dataset, 'resume_likelihood', lambda text: (True, []))
    monkeypatch.setattr(dataset, 'parse_cv', lambda name, content, **kwargs: CandidateRecord(name))
    assert prepare(source, output, 2)['prepared'] == 2
    assert prepare(source, output, 2)['prepared'] == 2
    paths = sorted(output.glob('batch_*/examples.jsonl'))
    ids = [row['id'] for path in paths for row in dataset.read_rows(path)]
    assert len(ids) == len(set(ids)) == 4
