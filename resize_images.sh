#!/bin/bash

# Check if correct number of arguments is provided
if [ "$#" -ne 2 ]; then
  echo "Usage: $0 <source_directory> <output_directory>"
  exit 1
fi

# Input arguments
SOURCE_DIR="$1"
OUTPUT_DIR="$2"

# Maximum dimensions
MAX_WIDTH=800
MAX_HEIGHT=600

# Create output directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

# Process each image in the source directory
for IMAGE in "$SOURCE_DIR"/*.{jpg,jpeg,png,gif}; do
  # Check if file exists (avoids issues if no images are found)
  [ -e "$IMAGE" ] || continue

  # Extract filename and extension
  FILENAME=$(basename "$IMAGE")
  
  # Resize image while maintaining aspect ratio
  magick convert "$IMAGE" -resize "${MAX_WIDTH}x${MAX_HEIGHT}>" "$OUTPUT_DIR/$FILENAME"
  
  echo "Resized $IMAGE -> $OUTPUT_DIR/$FILENAME"
done

echo "All images resized and saved to $OUTPUT_DIR."
