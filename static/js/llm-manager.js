async function populateLLMSettings() {
  try {
    const res = await fetch('/config');
    const payload = await res.json();
    const cfg = payload.config || {};
    const llmSection = cfg.LLM_SETTINGS || {};

    const providerField = document.getElementById('provider');
    const modelField = document.getElementById('model-name');
    const apiKeyField = document.getElementById('api-key');
    const personaField = document.getElementById('custom-instructions');

    if (providerField) {
      providerField.value = llmSection.provider || cfg.LLM_PROVIDER || providerField.value;
    }
    if (modelField && (llmSection.model || cfg.GPT_MODEL)) {
      modelField.value = llmSection.model || cfg.GPT_MODEL || '';
    }
    if (apiKeyField && (llmSection.api_key || cfg.OPENAI_API_KEY)) {
      apiKeyField.value = llmSection.api_key || cfg.OPENAI_API_KEY || '';
    }
    if (personaField && !personaField.value) {
      personaField.value = cfg.LLM_PERSONA || "Speak in a Friendly & Helpful tone.";
    }
  } catch (err) {
    console.error('Failed to populate LLM settings:', err);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const modelForm = document.getElementById('model-config-form');
  if (modelForm) {
    modelForm.addEventListener('submit', async (e) => {
      e.preventDefault();

      const provider = document.getElementById('provider').value;
      const model = document.getElementById('model-name').value;
      const apiKey = document.getElementById('api-key').value;
      const status = document.getElementById('llm-status');
      status.textContent = '⏳ Updating...';
      status.className = "status-message";

      try {
        const res = await fetch('/admin/update_llm', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider, model, api_key: apiKey }),
        });

        const data = await res.json();

        if (res.ok) {
          status.textContent = `✅ LLM updated: ${data.message}`;
          status.className = "status-message success";
        } else {
          status.textContent = `❌ Failed to update LLM: ${data.error || 'Unknown error'}`;
          status.className = "status-message error";
        }
      } catch (err) {
        status.textContent = `❌ Failed to update LLM`;
        status.className = "status-message error";
        console.error(err);
      }
    });
  }

  const personaForm = document.getElementById('persona-form');
  if (personaForm) {
    personaForm.addEventListener('submit', async (e) => {
      e.preventDefault();

      const customInstructions = document.getElementById('custom-instructions').value.trim();
      const status = document.getElementById('persona-status');

      status.textContent = '⏳ Updating persona...';
      status.className = "status-message";

      try {
        const res = await fetch('/update_llm/persona', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ custom_instructions: customInstructions }),
        });

        const data = await res.json();

        if (res.ok) {
          status.textContent = `✅ Persona updated`;
          status.className = "status-message success";
        } else {
          status.textContent = `❌ Failed to update persona: ${data.error || 'Unknown error'}`;
          status.className = "status-message error";
        }
      } catch (err) {
        status.textContent = `❌ Failed to update persona`;
        status.className = "status-message error";
        console.error(err);
      }
    });
  }

  populateLLMSettings();
});
