/**
 * Run webpack with: ./node_modules/.bin/webpack --config webpack.config.js
 */
const path = require('path');
const BundleTracker = require('webpack-bundle-tracker');
const webpack = require("webpack");

module.exports = {
    mode: 'production',
    stats: 'verbose',
    entry: {
        app: [
            './oldp/assets/static-global/js/index.js',
            // './oldp/assets/static-global/scss/style.scss'
            // './oldp/assets/static-global/js/autocomplete_light/jquery.init.js',
            // './oldp/assets/static-global/js/autocomplete_light/autocomplete.init.js',
            // './oldp/assets/static-global/js/autocomplete_light/forward.js',
            // './oldp/assets/static-global/js/autocomplete_light/select2.js',
            // './oldp/assets/static-global/js/autocomplete_light/jquery.post-setup.js',
        ]
    },
    output: {
        filename: '[name].js',
        path: path.resolve(__dirname, 'oldp/assets/static-global/dist')
    },
    plugins: [
        new BundleTracker({
            path: __dirname,
            filename: './oldp/assets/webpack-stats.json'
        }),
    ],
    module: {
        rules: [
            {
                test: /\.js$/, // include .js files
                exclude: /node_modules/, // exclude any and all files in the node_modules folder
                use: []
            }
        ]
    },
};
