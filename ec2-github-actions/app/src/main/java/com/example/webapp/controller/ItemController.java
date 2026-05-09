package com.example.webapp.controller;

import com.example.common.ResponseWrapper;
import com.example.webapp.model.Item;
import com.example.webapp.repository.ItemRepository;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

import java.util.List;

@Controller
public class ItemController {

    private final ItemRepository itemRepository;

    public ItemController(ItemRepository itemRepository) {
        this.itemRepository = itemRepository;
    }

    @GetMapping("/")
    public String index(Model model) {
        model.addAttribute("items", itemRepository.findAll());
        return "index";
    }

    @PostMapping("/items/add")
    public String add(@RequestParam String name) {
        if (name != null && !name.isBlank()) {
            itemRepository.add(name.trim());
        }
        return "redirect:/";
    }

    @PostMapping("/items/delete/{id}")
    public String delete(@PathVariable Long id) {
        itemRepository.delete(id);
        return "redirect:/";
    }

    /**
     * common-utils の ResponseWrapper を使った REST エンドポイント。
     * GitHub Packages から取得した共通ライブラリが実際に動作していることを確認できる。
     */
    @GetMapping("/api/items")
    @ResponseBody
    public ResponseWrapper<List<Item>> apiItems() {
        return ResponseWrapper.success(itemRepository.findAll());
    }

    @GetMapping("/api/health")
    @ResponseBody
    public ResponseWrapper<String> health() {
        return ResponseWrapper.success("OK");
    }
}
