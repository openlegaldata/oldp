/**
 * Run webpack with: ./node_modules/.bin/webpack --config webpack.config.js
 */
const path = require('path');
const MiniCssExtractPlugin = require("mini-css-extract-plugin");
const CleanWebpackPlugin = require('clean-webpack-plugin');
const CopyWebpackPlugin = require('copy-webpack-plugin');

const webpack = require("webpack");
const devMode = process.env.DJANGO_CONFIGURATION == 'Dev';

const distPath = path.resolve(__dirname, 'oldp/assets/static/dist');

console.log('devMode: ', devMode);

module.exports = {
    mode : devMode ? 'development' : 'production',
    // mode: 'production',
    devtool: 'source-map',
    entry : {
        main: './oldp/assets/static/js/main.js',
        // annotate: './oldp/assets/static-global/js/annotate.js'
    },
    output : {
        filename : '[name].js',
        path : distPath
    },
    // optimization: {
    //     splitChunks: {
    //         // include all types of chunks
    //         chunks: 'all'
    //     }
    // },
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
                    { loader: 'css-loader', options: { url: false, sourceMap: devMode } }, // Remove minimize here
                    { loader: 'sass-loader', options: { sourceMap: true, sassOptions: { outputStyle: 'compressed' } } } // Set compression directly in sassOptions
                ],
            }
        ]
    },
    plugins: [
        new CleanWebpackPlugin(distPath, {} ),
        new MiniCssExtractPlugin({
            filename: "style.css"
        }),
        new CopyWebpackPlugin({
            patterns: [
                { from: './node_modules/font-awesome/fonts', to: distPath + '/fonts/font-awesome'},
                { from: './node_modules/jquery-ui/themes/base/images', to: distPath + '/images'},
            ],
        })
    ],
    watchOptions: {
        ignored: /node_modules/
    }
};
