(function () {
  const transmissionColors = {
    60: "#5b2c83",
    115: "#2468a2",
    230: "#c51b2f"
  };

  function transmissionStyle(feature) {
    const voltage = Number(feature.properties.RATEDKV);
    return {
      color: transmissionColors[voltage] || "#59645f",
      opacity: .82,
      weight: voltage >= 230 ? 4 : voltage >= 115 ? 3.5 : 3
    };
  }

  function countyStyle() {
    return {
      color: "#17201c",
      dashArray: "8 6",
      fill: false,
      opacity: .9,
      weight: 2.5
    };
  }

  function substationMarker(latlng, pane = "infrastructure-stations", renderer) {
    return L.circleMarker(latlng, {
      pane,
      renderer,
      color: "#17201c",
      fillColor: "#ffd447",
      fillOpacity: .95,
      radius: 6,
      weight: 2
    });
  }

  function tooltip(properties, fields, escape) {
    return fields
      .filter(([key]) => properties[key] !== null && properties[key] !== undefined)
      .map(([key, label]) => `<b>${escape(label)}</b>: ${escape(properties[key])}`)
      .join("<br>");
  }

  window.MapInfrastructure = {
    countyStyle,
    substationMarker,
    tooltip,
    transmissionColors,
    transmissionStyle
  };
})();
