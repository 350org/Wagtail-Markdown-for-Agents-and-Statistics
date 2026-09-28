// From and To apply only with Custom dates; select it so typed dates are not ignored.
(() => {
    const preset = document.getElementById("id_preset");
    for (const id of ["id_start", "id_end"]) {
        document.getElementById(id)?.addEventListener("input", () => {
            if (preset) preset.value = "custom";
        });
    }
})();
