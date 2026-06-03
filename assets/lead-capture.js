(function () {
  const forms = document.querySelectorAll("[data-lead-form]");

  function setStatus(form, message, isError) {
    const status = form.querySelector(".lead-status");
    if (!status) return;
    status.textContent = message;
    status.classList.toggle("is-error", Boolean(isError));
  }

  function trackMetaLead(service) {
    if (typeof window.fbq !== "function") return;

    const normalizedService = (service || "unknown").trim().toLowerCase();
    window.fbq("track", "Lead", {
      content_name: `${normalizedService}_email_reservation`
    });
  }

  async function submitLead(form) {
    const input = form.querySelector('input[name="email"]');
    const button = form.querySelector('button[type="submit"]');
    const email = input ? input.value.trim() : "";

    if (!email) {
      setStatus(form, "이메일을 입력해 주세요.", true);
      return;
    }

    const payload = {
      service: form.dataset.service,
      email,
      language: form.dataset.language || document.documentElement.lang || "ko",
      ctaId: form.dataset.ctaId || "final",
      pagePath: window.location.pathname,
      sourceUrl: window.location.href
    };

    if (button) button.disabled = true;
    setStatus(form, "저장하는 중입니다...", false);

    try {
      const response = await fetch("/api/leads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      const result = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(result.detail || "저장하지 못했습니다.");
      }

      form.classList.add("is-sent");
      form.reset();
      setStatus(form, "신청이 접수되었습니다. 곧 안내 메일을 보내드릴게요.", false);
      trackMetaLead(payload.service);
    } catch (error) {
      setStatus(form, error.message || "잠시 후 다시 시도해 주세요.", true);
    } finally {
      if (button) button.disabled = false;
    }
  }

  forms.forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      submitLead(form);
    });
  });
})();
