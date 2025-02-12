#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <tiffio.h>
#include "xcliball.h"

#define SAVE_PATH "/home/jetson/captured_frames/"
#define NUM_FRAMES 100
#define FRAME_WIDTH 640
#define FRAME_HEIGHT 480
#define NUM_BUFFERS 3

unsigned short **frame_buffers;
TIFF *tiff;

// Function to initialize the frame grabber
int setup_frame_grabber() {
    int status = pxd_PIXCIopen("", "", "");
    if (status < 0) {
        printf("Error initializing PIXCI: %s\n", pxd_mesgErrorCode(status));
        return -1;
    }
    pxd_imageSizeXdim();
    pxd_imageSizeYdim();
    pxd_defineImage(1, 0, 0, FRAME_WIDTH, FRAME_HEIGHT, "");

    frame_buffers = malloc(NUM_BUFFERS * sizeof(unsigned short *));
    for (int i = 0; i < NUM_BUFFERS; i++) {
        frame_buffers[i] = (unsigned short *)malloc(FRAME_WIDTH * FRAME_HEIGHT * sizeof(unsigned short));
        if (!frame_buffers[i]) {
            printf("Error allocating frame buffer %d\n", i);
            return -1;
        }
    }
    return 0;
}

// Function to capture frames
void capture_frames() {
    int status = pxd_goLiveSeq(1, 1, NUM_BUFFERS, 1);
    if (status < 0) {
        printf("Error starting live capture: %s\n", pxd_mesgErrorCode(status));
        return;
    }

    char filename[256];
    for (int i = 0; i < NUM_FRAMES; i++) {
        int next_frame = i % NUM_BUFFERS;
        if (pxd_capturedBufferData(next_frame) == NULL) {
            printf("Error: No frame captured\n");
            break;
        }

        status = pxd_readushort(1, next_frame, 0, 0, FRAME_WIDTH, FRAME_HEIGHT, frame_buffers[next_frame], FRAME_WIDTH * FRAME_HEIGHT, "");
        if (status < 0) {
            printf("Error reading frame buffer %d: %s\n", next_frame, pxd_mesgErrorCode(status));
            break;
        }

        sprintf(filename, "%sframe_%d.tiff", SAVE_PATH, i);
        tiff = TIFFOpen(filename, "w");
        if (!tiff) {
            fprintf(stderr, "Error opening TIFF file for output\n");
            continue;
        }

        TIFFSetField(tiff, TIFFTAG_IMAGEWIDTH, FRAME_WIDTH);
        TIFFSetField(tiff, TIFFTAG_IMAGELENGTH, FRAME_HEIGHT);
        TIFFSetField(tiff, TIFFTAG_SAMPLESPERPIXEL, 1);
        TIFFSetField(tiff, TIFFTAG_BITSPERSAMPLE, 16);
        TIFFSetField(tiff, TIFFTAG_ORIENTATION, ORIENTATION_TOPLEFT);
        TIFFSetField(tiff, TIFFTAG_PHOTOMETRIC, PHOTOMETRIC_MINISBLACK);
        TIFFSetField(tiff, TIFFTAG_PLANARCONFIG, PLANARCONFIG_CONTIG);
        TIFFSetField(tiff, TIFFTAG_ROWSPERSTRIP, FRAME_HEIGHT);
        
        TIFFWriteEncodedStrip(tiff, 0, frame_buffers[next_frame], FRAME_WIDTH * FRAME_HEIGHT * sizeof(unsigned short));
        TIFFClose(tiff);
        printf("Saved frame %d\n", i);
    }
}

void cleanup() {
    for (int i = 0; i < NUM_BUFFERS; i++) {
        free(frame_buffers[i]);
    }
    free(frame_buffers);
    pxd_PIXCIclose();
}

int main() {
    if (setup_frame_grabber() != 0) return -1;
    capture_frames();
    cleanup();
    printf("Recording complete. Frames saved in %s\n", SAVE_PATH);
    return 0;
}