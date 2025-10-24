#!/bin/bash
cd image-search-frontend
ng build
cd ..
rm -rf image-search-backend/static/* && cp -r image-search-frontend/dist/image-search-frontend/* image-search-backend/static/
git add .
git commit -m "Deploy"
git push
