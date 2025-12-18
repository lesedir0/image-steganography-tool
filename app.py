import math
import streamlit as st
from PIL import Image
import io
import numpy as np
from reedsolo import RSCodec, ReedSolomonError
import struct

# --- CONFIGURATION ---
ECC_LEVEL = 10  # Error Correction Code level
rsc = RSCodec(ECC_LEVEL)

st.set_page_config(page_title="Image Steganography Tool", layout="centered", page_icon="🛡️")

# --- CORE FUNCTIONS ---

def calculate_psnr(original_img, stego_img):
    """Calculates Peak Signal-to-Noise Ratio to measure image quality."""
    if original_img.size != stego_img.size:
        return 0.0
    
    arr1 = np.array(original_img.convert("RGB")).astype(float)
    arr2 = np.array(stego_img.convert("RGB")).astype(float)
    
    mse = np.mean((arr1 - arr2) ** 2)
    if mse == 0:
        return 100.0 
    
    return 20 * math.log10(255.0 / math.sqrt(mse))

def bytes_to_bits(data_bytes):
    """Converts bytes to a numpy bit array."""
    return np.unpackbits(np.frombuffer(data_bytes, dtype=np.uint8))

def embed_data(image, raw_data):
    """Embeds binary data into the LSB (Least Significant Bit) of the image."""
    original_mode = image.mode
    
    # Standardize image to RGB/RGBA
    if original_mode == 'RGBA':
        image = image.convert("RGBA")
        r, g, b, a = image.split() 
        rgb_img = Image.merge("RGB", (r, g, b))
        img_array = np.array(rgb_img)
    else:
        image = image.convert("RGB")
        img_array = np.array(image)
        original_mode = 'RGB'

    flat_img = img_array.flatten() 
    
    # Capacity Check
    max_capacity = len(flat_img) 
    # 32 bits for header + data length + ECC overhead
    needed_space = 32 + (len(raw_data) + ECC_LEVEL) * 8
    
    if needed_space > max_capacity:
        return None, f"Insufficient Capacity! (Needed: {needed_space} bits, Available: {max_capacity} bits)"

    try:
        # Apply Reed-Solomon Error Correction
        encoded_data = rsc.encode(raw_data) 
        # Create a 4-byte header representing the length of the encoded data
        header = struct.pack('>I', len(encoded_data)) 
        full_payload = header + encoded_data
        payload_bits = bytes_to_bits(full_payload)
    except Exception as e:
        return None, f"Encoding Error: {e}"
    
    # Modify LSB of pixels
    flat_img[:len(payload_bits)] = (flat_img[:len(payload_bits)] & 254) | payload_bits
    
    # Reconstruct Image
    new_img_array = flat_img.reshape(img_array.shape)
    stego_rgb = Image.fromarray(new_img_array.astype('uint8'), 'RGB') 
    
    if original_mode == 'RGBA': 
        r, g, b = stego_rgb.split()
        final_img = Image.merge("RGBA", (r, g, b, a))
        return final_img, "Data embedded successfully (Alpha channel preserved)."
    
    return stego_rgb, "Data embedded successfully."

def extract_data(image):
    """Extracts hidden data from the LSB of the image."""
    img_array = np.array(image.convert("RGB"))
    flat_img = img_array.flatten()
    
    # Extract 32-bit Header
    length_bits = flat_img[:32] & 1     
    length_bytes = np.packbits(length_bits) 
    
    try:
        data_len = struct.unpack('>I', length_bytes)[0] 
    except:
        return None, "Failed to read header."
    
    if data_len > len(flat_img) // 8 or data_len == 0: 
        return None, "No hidden data detected."
    
    # Extract Payload
    total_bits = 32 + (data_len * 8)      
    data_bits = flat_img[32:total_bits] & 1    
    data_bytes = np.packbits(data_bits).tobytes()
    
    # Decode Reed-Solomon
    try:
        decoded_data = rsc.decode(bytearray(data_bytes))[0] 
        return decoded_data, "Success"
    except ReedSolomonError:
        return None, "Data is corrupted or incorrect ECC."
    except Exception as e:
        return None, f"Error: {e}"

# --- USER INTERFACE ---

st.title("🛡️ Image Steganography")
st.markdown("Securely hide messages or files inside images using LSB and Reed-Solomon Error Correction.")

tab1, tab2 = st.tabs(["🔒 ENCODE (Hide)", "🔓 DECODE (Read)"])

with tab1:
    with st.container(border=True):
        st.subheader("Step 1: Select Carrier Image")
        cover_file = st.file_uploader("Upload PNG or JPG", type=["png", "jpg", "jpeg"], key="encoder_upload")

    with st.container(border=True):
        st.subheader("Step 2: Prepare Secret Data")
        hide_type = st.radio("Data Type:", ["📝 Text Message", "📁 File / Image"], horizontal=True)
        
        secret_data = None
        if hide_type == "📝 Text Message":
            txt_input = st.text_area("Enter your message:", height=120, placeholder="Secret password...")
            if txt_input: secret_data = txt_input.encode('utf-8')
        else:
            secret_file = st.file_uploader("Select file to hide:", type=["png", "jpg", "jpeg", "txt", "pdf"])
            if secret_file: secret_data = secret_file.getvalue()

    if st.button("🔒 Encode & Download", type="primary", use_container_width=True):
        if cover_file and secret_data:
            cover_img = Image.open(cover_file)
            with st.spinner('Processing pixels...'):
                result_img, msg = embed_data(cover_img, secret_data)
                
            if result_img:
                st.success(msg)
                col1, col2 = st.columns(2)
                with col1:
                    psnr_val = calculate_psnr(cover_img, result_img)
                    st.metric("Image Quality (PSNR)", f"{psnr_val:.2f} dB")
                with col2:
                    buf = io.BytesIO()
                    result_img.save(buf, format="PNG")
                    st.download_button(
                        label="⬇️ Download Stego Image",
                        data=buf.getvalue(),
                        file_name="stego_output.png",
                        mime="image/png",
                        use_container_width=True
                    )
            else:
                st.error(msg)
        else:
            st.warning("Please upload an image and provide the secret data.")

with tab2:
    with st.container(border=True):
        st.subheader("Analyze Stego Image")
        stego_file = st.file_uploader("Upload the PNG image containing data:", type=["png"], key="decoder_upload")
    
    if stego_file and st.button("🔓 Decode & Extract", type="primary", use_container_width=True):
        stego_img = Image.open(stego_file)
        with st.spinner('Recovering data...'):
            decoded_raw, msg = extract_data(stego_img)
            
        if decoded_raw:
            decoded_bytes = bytes(decoded_raw)
            st.success("Data successfully recovered! ✅")
            
            # Try to display as image
            is_image = False
            try:
                with io.BytesIO(decoded_bytes) as buf:
                    img_check = Image.open(buf)
                    img_check.verify()
                    buf.seek(0)
                    final_img = Image.open(buf)
                    st.image(final_img, caption="Hidden Image", width=400)
                    
                    save_buf = io.BytesIO()
                    final_img.save(save_buf, format="PNG")
                    st.download_button("🖼️ Save Extracted Image", save_buf.getvalue(), "extracted.png", "image/png")
                    is_image = True
            except:
                pass
            
            if not is_image:
                try:
                    text = decoded_bytes.decode('utf-8')
                    st.code(text, language="text")
                    st.download_button("📄 Save Extracted Text", decoded_bytes, "message.txt")
                except:
                    st.warning("Binary data detected.")
                    st.download_button("💾 Save Binary File", decoded_bytes, "hidden_data.bin")
        else:
            st.error(f"Error: {msg}")
