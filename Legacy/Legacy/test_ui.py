import webview

# Create the window
window = webview.create_window('X4 Save Data Tool Test', 'https://flowrl.com')

# Explicitly use the 'qt' engine to keep the window open
webview.start(gui='qt')
