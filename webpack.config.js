/**
 * Run webpack with: ./node_modules/.bin/webpack --config webpack.config.js
 */
const path = require('path');
const BundleTracker = require('webpack-bundle-tracker');
const ExtractTextPlugin = require('extract-text-webpack-plugin');
const MiniCssExtractPlugin = require("mini-css-extract-plugin");
const CleanWebpackPlugin = require('clean-webpack-plugin');
const CopyWebpackPlugin = require('copy-webpack-plugin');

const webpack = require("webpack");
const devMode = process.env.NODE_ENV !== 'production';

const distPath = path.resolve(__dirname, 'oldp/assets/static-global/dist');

module.exports = {
    entry : './oldp/assets/static-global/js/index.js',
    output : {
        filename : 'app.js',
        path : distPath
    },
    module : {
        rules : [
            {
                test: /\.js$/,
                exclude: /node_modules/,
                // use: "babel-loader"
            },
            {
                test: /\.scss$/,
                use: [
                    { loader: MiniCssExtractPlugin.loader, options: {} },
                    { loader: 'css-loader', options: { url: false, sourceMap: true } },
                    { loader: 'sass-loader', options: { sourceMap: true } }
                ],
            }
        ]
    },
    devtool: 'source-map',
    plugins: [
        new CleanWebpackPlugin(distPath, {} ),
        new MiniCssExtractPlugin({
            filename: "style.css"
        }),
        new CopyWebpackPlugin([
            // TODO load with file-loader automatically
            { from: './node_modules/font-awesome/fonts', to: distPath + '/fonts/font-awesome'},
            { from: './node_modules/jquery-ui/themes/base/images', to: distPath + '/images'},

        ])
    ],
    watchOptions: {
        ignored: /node_modules/
    },
    mode : devMode ? 'development' : 'production'
};
