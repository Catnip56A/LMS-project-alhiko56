/*
 * Admin quiz-question inline form enhancement (lms/admin/__init__.py QuizView).
 * The real fields the server reads are still the raw `options`/`correct_answer`
 * JSON textareas — this just builds a friendlier UI on top and keeps those
 * textareas in sync so submission is unchanged. Works for both existing rows
 * (rendered server-side) and rows added via Flask-Admin's "Add Questions" button.
 */
(function () {
    function findRow(el) {
        return el.closest('.inline-field.card');
    }

    function getFields(row) {
        return {
            typeSelect: row.querySelector('select[name$="question_type"]'),
            optionsTextarea: row.querySelector('textarea[name$="options"]'),
            answerTextarea: row.querySelector('textarea[name$="correct_answer"]'),
        };
    }

    function safeParse(raw, fallback) {
        try {
            var parsed = JSON.parse(raw);
            return parsed === undefined ? fallback : parsed;
        } catch (e) {
            return fallback;
        }
    }

    function ensureBuilderUI(row, fields) {
        if (row._qb) return row._qb;

        var optionsGroup = fields.optionsTextarea.closest('.form-group');
        var answerGroup = fields.answerTextarea.closest('.form-group');

        var builder = document.createElement('div');
        builder.className = 'qb-builder';

        // --- options builder (MCQ) ---
        var optionsWrap = document.createElement('div');
        optionsWrap.className = 'form-group qb-options-wrap';
        var optionsLabel = document.createElement('label');
        optionsLabel.textContent = 'Options';
        optionsLabel.className = 'col-form-label';
        var optionsList = document.createElement('div');
        var addOptionBtn = document.createElement('button');
        addOptionBtn.type = 'button';
        addOptionBtn.className = 'btn btn-sm btn-outline-secondary mt-1';
        addOptionBtn.textContent = '+ Add Option';
        optionsWrap.appendChild(optionsLabel);
        optionsWrap.appendChild(optionsList);
        optionsWrap.appendChild(addOptionBtn);

        // --- correct answer builder (mode depends on question type) ---
        var answerWrap = document.createElement('div');
        answerWrap.className = 'form-group qb-answer-wrap';
        var answerLabel = document.createElement('label');
        answerLabel.textContent = 'Correct Answer';
        answerLabel.className = 'col-form-label';

        var answerMcqSelect = document.createElement('select');
        answerMcqSelect.className = 'form-control qb-answer-mcq';

        var answerTfSelect = document.createElement('select');
        answerTfSelect.className = 'form-control qb-answer-tf';
        ['true', 'false'].forEach(function (v) {
            var opt = document.createElement('option');
            opt.value = v;
            opt.textContent = v === 'true' ? 'True' : 'False';
            answerTfSelect.appendChild(opt);
        });

        var answerTextInput = document.createElement('input');
        answerTextInput.type = 'text';
        answerTextInput.className = 'form-control qb-answer-text';
        answerTextInput.placeholder = 'Expected answer text';

        answerWrap.appendChild(answerLabel);
        answerWrap.appendChild(answerMcqSelect);
        answerWrap.appendChild(answerTfSelect);
        answerWrap.appendChild(answerTextInput);

        builder.appendChild(optionsWrap);
        builder.appendChild(answerWrap);
        optionsGroup.parentNode.insertBefore(builder, optionsGroup);
        optionsGroup.style.display = 'none';
        answerGroup.style.display = 'none';

        function currentOptionTexts() {
            return Array.prototype.slice.call(optionsList.querySelectorAll('input[type="text"]'))
                .map(function (i) { return i.value; });
        }

        function syncOptionsTextarea() {
            fields.optionsTextarea.value = JSON.stringify(currentOptionTexts());
            refreshAnswerChoices();
        }

        function refreshAnswerChoices() {
            var opts = currentOptionTexts();
            var prev = answerMcqSelect.value;
            answerMcqSelect.innerHTML = '';
            opts.forEach(function (text, idx) {
                var opt = document.createElement('option');
                opt.value = String(idx);
                opt.textContent = idx + ': ' + (text || '(empty)');
                answerMcqSelect.appendChild(opt);
            });
            if (prev !== '' && opts[parseInt(prev, 10)] !== undefined) {
                answerMcqSelect.value = prev;
            }
        }

        function addOptionRow(value) {
            var optRow = document.createElement('div');
            optRow.className = 'input-group mb-1';
            var input = document.createElement('input');
            input.type = 'text';
            input.className = 'form-control';
            input.value = value || '';
            input.addEventListener('input', syncOptionsTextarea);
            var removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'btn btn-outline-danger';
            removeBtn.textContent = '×';
            removeBtn.addEventListener('click', function () {
                optRow.remove();
                syncOptionsTextarea();
            });
            optRow.appendChild(input);
            optRow.appendChild(removeBtn);
            optionsList.appendChild(optRow);
        }

        addOptionBtn.addEventListener('click', function () {
            addOptionRow('');
            syncOptionsTextarea();
        });
        answerMcqSelect.addEventListener('change', function () {
            fields.answerTextarea.value = answerMcqSelect.value;
        });
        answerTfSelect.addEventListener('change', function () {
            fields.answerTextarea.value = answerTfSelect.value;
        });
        answerTextInput.addEventListener('input', function () {
            fields.answerTextarea.value = JSON.stringify(answerTextInput.value);
        });

        // Seed the builder from whatever's already in the raw fields (edit mode / server defaults)
        var existingOptions = safeParse(fields.optionsTextarea.value, []);
        if (!Array.isArray(existingOptions)) existingOptions = [];
        existingOptions.forEach(function (text) { addOptionRow(text); });
        syncOptionsTextarea();

        var existingAnswer = safeParse(fields.answerTextarea.value, null);
        if (typeof existingAnswer === 'number') {
            answerMcqSelect.value = String(existingAnswer);
        } else if (typeof existingAnswer === 'boolean') {
            answerTfSelect.value = existingAnswer ? 'true' : 'false';
        } else if (typeof existingAnswer === 'string') {
            answerTextInput.value = existingAnswer;
        }

        row._qb = {
            optionsWrap: optionsWrap,
            answerMcqSelect: answerMcqSelect,
            answerTfSelect: answerTfSelect,
            answerTextInput: answerTextInput,
        };
        return row._qb;
    }

    function applyMode(row, fields) {
        var qb = ensureBuilderUI(row, fields);
        var type = fields.typeSelect.value;

        qb.optionsWrap.style.display = (type === 'mcq') ? '' : 'none';
        qb.answerMcqSelect.style.display = (type === 'mcq') ? '' : 'none';
        qb.answerTfSelect.style.display = (type === 'true_false') ? '' : 'none';
        qb.answerTextInput.style.display = (type === 'short_answer') ? '' : 'none';

        if (type === 'mcq') {
            fields.answerTextarea.value = qb.answerMcqSelect.value || '0';
        } else if (type === 'true_false') {
            fields.answerTextarea.value = qb.answerTfSelect.value || 'true';
        } else {
            fields.answerTextarea.value = JSON.stringify(qb.answerTextInput.value || '');
        }
    }

    function initRow(row) {
        var fields = getFields(row);
        if (!fields.typeSelect || !fields.optionsTextarea || !fields.answerTextarea) return;
        applyMode(row, fields);
    }

    function initAll() {
        document.querySelectorAll('.inline-field-list .inline-field.card').forEach(initRow);
    }

    document.addEventListener('change', function (e) {
        if (e.target.matches && e.target.matches('select[name$="question_type"]')) {
            var row = findRow(e.target);
            if (row) applyMode(row, getFields(row));
        }
    });

    document.addEventListener('click', function (e) {
        if (e.target.closest && e.target.closest('#questions-button')) {
            // Let Flask-Admin's clone-and-append finish first
            setTimeout(initAll, 50);
        }
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
})();
