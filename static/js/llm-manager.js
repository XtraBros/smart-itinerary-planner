  // LLM config update handler
  document.getElementById('model-config-form').addEventListener('submit', async (e) => {
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