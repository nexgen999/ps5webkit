/* payloads1.js - sous-listes de la liste principale "Linux Loader".
 *
 * Chaque fichier de payloads declare ses sous-listes avec :
 *   window.registerPayloadGroup({ category, id, label, tiles: [...] })
 * avec category = "hen" | "linux" | "utility".
 *
 * Un tile accepte { title, name, desc, key } ; seul `name` (le fichier envoye
 * au chargeur ELF) est obligatoire. window.PAYLOAD_TILES reste alimente pour
 * les pages qui ne connaissent que l'ancien format.
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

  var WIGGLEZ = [
    tile("Loader 12.00 - Pro", "ps5-linux-loader-1200-pro_Wigglez-sudo.elf", "Wigglez - sudo"),
    tile("Loader 12.02 - Pro", "ps5-linux-loader-1202-pro_Wigglez-sudo.elf", "Wigglez - sudo"),
    tile("Loader 12.20 - Pro", "ps5-linux-loader-1220-pro_Wigglez-sudo.elf", "Wigglez - sudo"),
    tile("Loader 12.40 - Pro", "ps5-linux-loader-1240-pro_Wigglez-sudo.elf", "Wigglez - sudo"),
    tile("Loader 12.60 - Pro", "ps5-linux-loader-1260-pro_Wigglez-sudo.elf", "Wigglez - sudo"),
    tile("Loader 12.70 - Pro", "ps5-linux-loader-1270-pro_Wigglez-sudo.elf", "Wigglez - sudo"),
    tile("Loader 12.xx - AIO", "ps5-linux-loader-12xx-aio_Wigglez-sudo.elf", "Wigglez - sudo"),
    tile("Loader 12.xx - Pro AIO", "ps5-linux-loader-12xx-pro-aio_Wigglez-sudo.elf", "Wigglez - sudo"),
    tile("Loader 3.xx à 13.xx - AIO", "ps5-linux-loader-3x-13x-aio_Wigglez-sudo.elf", "Wigglez - sudo")
  ];

  var SONIC = [
    tile("Loader 10.xx", "ps5-linux-loader-10x_soniciso.elf", "Sonic_Iso"),
    tile("Loader 11.xx à 13.xx", "ps5-linux-loader-11x-13x_soniciso.elf", "Sonic_Iso"),
    tile("Loader 13.60 - Pro", "ps5-linux-loader-13.60-pro_soniciso.elf", "Sonic_Iso"),
    tile("Loader 10 à 13 - build 02.11", "ps5-linux-loader-all10-13-20261102_soniciso.elf", "Sonic_Iso"),
    tile("Loader 10 à 13 - Pro - build 03.11", "ps5-linux-loader-all10-13-20261103-pro_soniciso.elf", "Sonic_Iso")
  ];

  var AUTRES = [
    tile("Loader 9.40 - all", "ps5-linux-loader-9.40-all_Arksama.elf", "Arksama"),
    tile("Loader 11.60", "ps5-linux-loader-11.60_sajadsrc.elf", "sajadsrc"),
    tile("Loader toutes versions", "ps5-linux-loader_TheRealRexo.elf", "TheRealRexo")
  ];

  if (typeof window.registerPayloadGroup === "function") {
    window.registerPayloadGroup({ category: "linux", id: "wigglez", label: "Wigglez - sudo", tiles: WIGGLEZ });
    window.registerPayloadGroup({ category: "linux", id: "sonic", label: "Sonic_Iso", tiles: SONIC });
    window.registerPayloadGroup({ category: "linux", id: "autres", label: "Autres loaders", tiles: AUTRES });
  }

  /* Compatibilite ancien format. */
  window.PAYLOAD_TILES = WIGGLEZ.concat(SONIC, AUTRES);
  window.PAYLOAD_ART = window.PAYLOAD_ART || { dir: "ui/", pfx: "btn-", on: true };
})();
