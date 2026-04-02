<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor
  version="1.0.0"
  xmlns="http://www.opengis.net/sld"
  xmlns:ogc="http://www.opengis.net/ogc"
  xmlns:xlink="http://www.w3.org/1999/xlink"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.opengis.net/sld http://schemas.opengis.net/sld/1.0.0/StyledLayerDescriptor.xsd">
  <NamedLayer>
    <Name>slopes</Name>
    <UserStyle>
      <Title>Pentes cyclables par difficulte</Title>
      <FeatureTypeStyle>

        <Rule>
          <Name>leger</Name>
          <Title>Leger (2-4%)</Title>
          <ogc:Filter>
            <ogc:PropertyIsEqualTo>
              <ogc:PropertyName>difficulty</ogc:PropertyName>
              <ogc:Literal>leger</ogc:Literal>
            </ogc:PropertyIsEqualTo>
          </ogc:Filter>
          <LineSymbolizer>
            <Stroke>
              <CssParameter name="stroke">#4CAF50</CssParameter>
              <CssParameter name="stroke-width">2</CssParameter>
              <CssParameter name="stroke-opacity">0.8</CssParameter>
            </Stroke>
          </LineSymbolizer>
        </Rule>

        <Rule>
          <Name>modere</Name>
          <Title>Modere (4-8%)</Title>
          <ogc:Filter>
            <ogc:PropertyIsEqualTo>
              <ogc:PropertyName>difficulty</ogc:PropertyName>
              <ogc:Literal>modere</ogc:Literal>
            </ogc:PropertyIsEqualTo>
          </ogc:Filter>
          <LineSymbolizer>
            <Stroke>
              <CssParameter name="stroke">#FFC107</CssParameter>
              <CssParameter name="stroke-width">3</CssParameter>
              <CssParameter name="stroke-opacity">0.85</CssParameter>
            </Stroke>
          </LineSymbolizer>
        </Rule>

        <Rule>
          <Name>difficile</Name>
          <Title>Difficile (8-12%)</Title>
          <ogc:Filter>
            <ogc:PropertyIsEqualTo>
              <ogc:PropertyName>difficulty</ogc:PropertyName>
              <ogc:Literal>difficile</ogc:Literal>
            </ogc:PropertyIsEqualTo>
          </ogc:Filter>
          <LineSymbolizer>
            <Stroke>
              <CssParameter name="stroke">#FF5722</CssParameter>
              <CssParameter name="stroke-width">4</CssParameter>
              <CssParameter name="stroke-opacity">0.9</CssParameter>
            </Stroke>
          </LineSymbolizer>
        </Rule>

        <Rule>
          <Name>tres_difficile</Name>
          <Title>Tres difficile (sup 12%)</Title>
          <ogc:Filter>
            <ogc:PropertyIsEqualTo>
              <ogc:PropertyName>difficulty</ogc:PropertyName>
              <ogc:Literal>tres_difficile</ogc:Literal>
            </ogc:PropertyIsEqualTo>
          </ogc:Filter>
          <LineSymbolizer>
            <Stroke>
              <CssParameter name="stroke">#B71C1C</CssParameter>
              <CssParameter name="stroke-width">5</CssParameter>
              <CssParameter name="stroke-opacity">0.95</CssParameter>
            </Stroke>
          </LineSymbolizer>
        </Rule>

      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
