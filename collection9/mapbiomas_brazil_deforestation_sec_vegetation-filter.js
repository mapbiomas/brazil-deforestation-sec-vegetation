//
var asset = 'projects/mapbiomas-workspace/COLECAO9/PRODUTOS-1/desmatamento-vegetacao-secundaria';
var assetOutput = 'projects/mapbiomas-workspace/COLECAO9/PRODUTOS-1/desmatamento-vegetacao-secundaria-ft';

var inputVersion = '0-24-4';
var outputVersion = '0-24-4e';

var groupSize = 12; //1ha

var groupSizeException = 34; //3ha

var years = [
    1985, 1986,
    1987, 1988, 1989, 1990,
    1991, 1992, 1993, 1994,
    1995, 1996, 1997, 1998,
    1999, 2000, 2001, 2002,
    2003, 2004, 2005, 2006,
    2007, 2008, 2009, 2010,
    2011, 2012, 2013, 2014,
    2015, 2016, 2017, 2018,
    2019, 2020, 2021, 2022,
    2023
];

var yearsException = [
    2023
];

// product properties
var properties = {
    "description": "# Desmatamento e Vegetação Secundária\n" +
        "Versao com filtro espacial de 2ha acumulado com ajuste para o ultimo ano\n" +
        "## 1. Descrição do dado:\n " +
        "   * Versão da integração: " + inputVersion + "\n" +
        "   * Versão do produto: " + outputVersion + "\n",
    "version": outputVersion,
    "territory": "BRAZIL",
    "collection_id": 9.0,
    "source": "GT desmatamento",
    "theme": "Desmatamento"
};

var transitions = ee.ImageCollection(asset)
    .filter(ee.Filter.eq('version', inputVersion))
    .min();

print(transitions);

var visTransitions = {
    min: 0,
    max: 7,
    format: 'png',
    bands: 'classification_2023',
    palette: [
        '#ffffff', // [0] No data
        '#faf5d1', // [1] Antrópico
        '#3f7849', // [2] Veg. Primária
        '#5bcf20', // [3] Veg. Secundária
        '#ea1c1c', // [4] Supressão Veg. Primária
        '#b4f792', // [5] Recuperação para Veg. Secundária
        '#fe9934', // [6] Supressão Veg. Secundária
        '#303149', // [7] Outras transições
    ]
};

Map.addLayer(transitions, visTransitions, 'transitions');

var dfMask = years.map(
    function (year) {
        var band = 'classification_' + year.toString();

        var dfYear = transitions.select(band)
            .remap([4, 6], [1, 1], 0);

        return dfYear.rename(band);
    }
);

dfMask = ee.Image(dfMask).reduce(ee.Reducer.anyNonZero());

var svMask = years.map(
    function (year) {
        var band = 'classification_' + year.toString();

        var svYear = transitions.select(band)
            .remap([3, 5], [1, 1], 0);

        return svYear.rename(band);
    }
);

svMask = ee.Image(svMask).reduce(ee.Reducer.max());

var dfMaskException = yearsException.map(
    function (year) {
        var band = 'classification_' + year.toString();

        var dfYear = transitions.select(band)
            .remap([4, 6], [1, 1], 0);

        return dfYear.rename(band);
    }
);

dfMaskException = ee.Image(dfMaskException).reduce(ee.Reducer.anyNonZero());
//
var dfConnected = dfMask.selfMask()
    .connectedPixelCount({
        maxSize: 100,
        eightConnected: true
    });

var svConnected = svMask.selfMask()
    .connectedPixelCount({
        maxSize: 100,
        eightConnected: true
    });

var dfConnectedException = dfMaskException.selfMask()
    .connectedPixelCount({
        maxSize: 100,
        eightConnected: true
    });
//

var transitionsFt = transitions;

transitionsFt = transitionsFt.where(dfConnected.lte(groupSize).and(transitionsFt.eq(4)), 7)
transitionsFt = transitionsFt.where(dfConnected.lte(groupSize).and(transitionsFt.eq(6)), 7)
transitionsFt = transitionsFt.where(svConnected.lte(groupSize).and(transitionsFt.eq(3)), 7)
transitionsFt = transitionsFt.where(svConnected.lte(groupSize).and(transitionsFt.eq(5)), 7);

// Apply exceptions for last years
var transitionsException = yearsException.map(
    function (year) {
        var band = 'classification_' + year.toString();

        var transitionsYear = transitionsFt.select(band);

        transitionsYear = transitionsYear.where(dfConnectedException.lte(groupSizeException).and(transitionsYear.eq(4)), 7);
        transitionsYear = transitionsYear.where(dfConnectedException.lte(groupSizeException).and(transitionsYear.eq(6)), 7);

        return transitionsYear;
    }
);

transitionsException = ee.Image(transitionsException);

print('transitionsException', transitionsException);

Map.addLayer(transitionsFt, visTransitions, 'transitions ft');
Map.addLayer(transitionsException, visTransitions, 'transitions Exception');

// add transitions exception to bands
transitionsFt = transitionsFt.addBands(transitionsException, null, true);

Map.addLayer(dfConnected.gte(groupSize).selfMask(), {
    min: 0,
    max: 1,
    format: 'png',
    palette: [
        '#0c003d',
        '#000000',
    ]
},
    "dfConnected",
    false,
    0.4
);

Map.addLayer(svConnected.gte(groupSize).selfMask(), {
    min: 0,
    max: 1,
    format: 'png',
    palette: [
        '#0c003d',
        '#000000',
    ]
},
    "svConnected",
    false,
    0.4
);

//
var assetGrids = 'projects/mapbiomas-workspace/AUXILIAR/cartas';

var grids = ee.FeatureCollection(assetGrids);

var gridNames = [
    "NA-19", "NA-20", "NA-21", "NA-22", "NB-20", "NB-21", "NB-22", "SA-19",
    "SA-20", "SA-21", "SA-22", "SA-23", "SA-24", "SB-18", "SB-19", "SB-20",
    "SB-21", "SB-22", "SB-23", "SB-24", "SB-25", "SC-18", "SC-19", "SC-20",
    "SC-21", "SC-22", "SC-23", "SC-24", "SC-25", "SD-20", "SD-21", "SD-22",
    "SD-23", "SD-24", "SE-20", "SE-21", "SE-22", "SE-23", "SE-24", "SF-21",
    "SF-22", "SF-23", "SF-24", "SG-21", "SG-22", "SG-23", "SH-21", "SH-22",
    "SI-22"
];

gridNames.forEach(
    function (gridName) {
        var grid = grids.filter(ee.Filter.stringContains('grid_name', gridName))

        Export.image.toAsset({
            image: transitionsFt.set(properties),
            description: gridName + "-" + outputVersion,
            assetId: assetOutput + "/" + gridName + "-" + outputVersion,
            pyramidingPolicy: {
                '.default': 'mode'
            },
            region: grid.geometry().buffer(300).bounds(),
            scale: 30,
            maxPixels: 1e13
        });
    }
);