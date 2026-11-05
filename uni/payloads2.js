/* payloads2.js - sous-listes des listes principales "HEN Loader" et "Utility".
 *
 * Meme contrat que payloads1.js : window.registerPayloadGroup({ category,
 * id, label, tiles }) avec category = "hen" | "linux" | "utility".
 */
(function () {
  "use strict";

  function tile(title, name, desc) {
    return {
      title: title,
      name: name,
      desc: desc || "",
      key: String(name).replace(/\.elf$/i, "")
    };
  }

  var HEN = [
    tile("ELF loader 13.60", "elfldr-ps5-1360.elf", "elfldr dédié FW 13.60"),
    tile("Bundle payload.elf", "payload.elf", "Binaire fourni - envoi long (2,4 Mo)")
  ];

  var HYPERVISEUR = [
    tile("Byepervisor - reborn", "byepervisor_reborn.elf", "Hyperviseur"),
    tile("Byepervisor - reborn fix", "byepervisor_reborn-fix.elf", "Hyperviseur corrigé")
  ];

  if (typeof window.registerPayloadGroup === "function") {
    window.registerPayloadGroup({ category: "hen", id: "hen", label: "Elfldr & HEN", tiles: HEN });
    window.registerPayloadGroup({ category: "utility", id: "hyperviseur", label: "Hyperviseur", tiles: HYPERVISEUR });
  }

  /* Compatibilite ancien format. */
  window.PAYLOAD_TILES = HEN.concat(HYPERVISEUR);
  window.PAYLOAD_ART = window.PAYLOAD_ART || { dir: "ui/", pfx: "btn-", on: true };
})();
